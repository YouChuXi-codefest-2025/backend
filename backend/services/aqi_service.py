# backend/services/aqi_service.py
from __future__ import annotations
import os, tempfile
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Iterable, Dict, Any

import cdsapi
import xarray as xr
from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from models import AqiCache

# ---- 時區與 CAMS 參數 ----
TW_TZ = timezone(timedelta(hours=8))
DATASET = "cams-global-atmospheric-composition-forecasts"
TAIPEI_AREA = [25.3, 121.3, 24.9, 121.7]
LEAD_HOURS = [0, 3, 6, 9, 12, 15, 18, 21, 24]
RUN_TIMES = ["00:00", "12:00"]

# ---- Bucket 精度（度）----
BUCKET_DECIMALS = int(os.getenv("AQI_BUCKET_DECIMALS", "3"))  # 0.001 度 ≈ 110m

def _floor_to_10min_utc(now: datetime) -> datetime:
    """將時間對齊到『10 分鐘的整數倍』ts（以 UTC 回傳）。"""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    # 以「台北時間」判斷整 10 分鐘，然後轉回 UTC 存
    now_tw = now.astimezone(TW_TZ)
    floored_tw = now_tw.replace(minute=(now_tw.minute // 10) * 10, second=0, microsecond=0)
    return floored_tw.astimezone(timezone.utc)

def _is_exact_10min_boundary(now: datetime) -> bool:
    now_tw = now.astimezone(TW_TZ)
    return now_tw.minute % 10 == 0 and now_tw.second == 0

def _iter_latest_refs(now_utc: datetime) -> Iterable[Tuple[str, str]]:
    today = now_utc.date()
    yesterday = today - timedelta(days=1)
    for d in (today, yesterday):
        for t in reversed(RUN_TIMES):
            yield (str(d), t)

def _build_cds_client() -> cdsapi.Client:
    url = os.getenv("CDS_API_URL", "https://ads.atmosphere.copernicus.eu/api")
    key = os.getenv("CDS_API_KEY")  # <uid>:<api-key>
    if key:
        return cdsapi.Client(url=url, key=key, verify=1)
    return cdsapi.Client(verify=1)

def _to_ug_per_m3(da: xr.DataArray) -> xr.DataArray:
    units = (da.attrs.get("units") or "").lower()
    out = da
    if "kg" in units:
        out = da * 1e9
        out.attrs["units"] = "µg m-3"
    return out

def _pm25_to_aqi_us_epa(pm25_ugm3: float) -> Tuple[int, str]:
    bp = [
        (0.0, 12.0, 0, 50, "Good"),
        (12.1, 35.4, 51, 100, "Moderate"),
        (35.5, 55.4, 101, 150, "Unhealthy for Sensitive Groups"),
        (55.5, 150.4, 151, 200, "Unhealthy"),
        (150.5, 250.4, 201, 300, "Very Unhealthy"),
        (250.5, 500.4, 301, 500, "Hazardous"),
    ]
    c = max(0.0, min(pm25_ugm3, 500.4))
    for c_low, c_high, i_low, i_high, cat in bp:
        if c_low <= c <= c_high:
            aqi = round((i_high - i_low) / (c_high - c_low) * (c - c_low) + i_low)
            return aqi, cat
    return 500, "Hazardous"

def _open_pm25_of_nearest(lat: float, lon: float, nc_path: str) -> Tuple[float, Dict[str, Any]]:
    with xr.open_dataset(nc_path) as ds:
        var = "pm2p5"
        if var not in ds.variables:
            raise RuntimeError(f"variable '{var}' not found; vars={list(ds.variables)}")
        da = _to_ug_per_m3(ds[var])
        sub = da.sel(latitude=lat, longitude=lon, method="nearest")
        for dim in ("forecast_period", "forecast_reference_time", "valid_time"):
            if dim in sub.dims:
                sub = sub.mean(dim=dim)
        val = float(sub.item())
        gp_lat = float(sub.coords.get("latitude").values if "latitude" in sub.coords else lat)
        gp_lon = float(sub.coords.get("longitude").values if "longitude" in sub.coords else lon)
        return val, {"grid_lat": gp_lat, "grid_lon": gp_lon}

def _bucket(v: float) -> float:
    # 四捨五入到 BUCKET_DECIMALS 位
    return round(v, BUCKET_DECIMALS)

def _get_from_cache(session: Session, slot_ts_utc: datetime, lat: float, lon: float) -> Optional[AqiCache]:
    lat_b = _bucket(lat)
    lon_b = _bucket(lon)
    q = (
        select(AqiCache)
        .where(
            and_(
                AqiCache.slot_ts == slot_ts_utc,
                AqiCache.lat_bucket == lat_b,
                AqiCache.lon_bucket == lon_b,
            )
        )
        .limit(1)
    )
    return session.execute(q).scalar_one_or_none()

def _get_from_cache_by_grid(session: Session, slot_ts_utc: datetime, grid_lat: float, grid_lon: float) -> Optional[AqiCache]:
    """根據實際的 CAMS 網格點座標查詢快取"""
    q = (
        select(AqiCache)
        .where(
            and_(
                AqiCache.slot_ts == slot_ts_utc,
                AqiCache.grid_lat == grid_lat,
                AqiCache.grid_lon == grid_lon,
            )
        )
        .limit(1)
    )
    return session.execute(q).scalar_one_or_none()

def _get_latest_any_slot(session: Session, lat: float, lon: float) -> Optional[AqiCache]:
    lat_b = _bucket(lat); lon_b = _bucket(lon)
    q = (
        select(AqiCache)
        .where(and_(AqiCache.lat_bucket == lat_b, AqiCache.lon_bucket == lon_b))
        .order_by(AqiCache.slot_ts.desc())
        .limit(1)
    )
    return session.execute(q).scalar_one_or_none()

def _fetch_and_upsert(session: Session, slot_ts_utc: datetime, lat: float, lon: float) -> AqiCache:
    """打 CAMS，取得 PM2.5，寫入 aqi_cache（若同網格點已有快取則直接使用）"""
    cli = _build_cds_client()
    used_ref: Optional[str] = None

    with tempfile.TemporaryDirectory() as td:
        nc_path = os.path.join(td, "cams_pm25_latest.nc")
        now_utc = datetime.now(timezone.utc)
        for date_str, time_str in _iter_latest_refs(now_utc):
            req = {
                "date": date_str,
                "type": "forecast",
                "format": "netcdf",
                "time": [time_str],
                "leadtime_hour": LEAD_HOURS,
                "variable": ["particulate_matter_2.5um"],
                "area": TAIPEI_AREA,
            }
            try:
                cli.retrieve(DATASET, req).download(nc_path)
                used_ref = f"{date_str} {time_str} UTC"
                break
            except Exception:
                continue

        if not used_ref or not os.path.exists(nc_path):
            raise RuntimeError("no CAMS data available")

        pm25, meta = _open_pm25_of_nearest(lat, lon, nc_path)
        grid_lat = meta.get("grid_lat")
        grid_lon = meta.get("grid_lon")

        # 檢查是否已有相同網格點和時間 slot 的快取
        if grid_lat is not None and grid_lon is not None:
            grid_cached = _get_from_cache_by_grid(session, slot_ts_utc, grid_lat, grid_lon)
            if grid_cached:
                # 找到相同網格點的快取，直接回傳（避免重複請求 API）
                return grid_cached

    rec = AqiCache(
        slot_ts=slot_ts_utc,
        lat=lat, lon=lon,
        lat_bucket=_bucket(lat), lon_bucket=_bucket(lon),
        grid_lat=grid_lat, grid_lon=grid_lon,
        pm25_ugm3=pm25,
        cams_reference_time=used_ref,
    )
    session.add(rec)
    try:
        session.commit()
    except Exception:
        session.rollback()
        # 發生唯一鍵衝突時，直接取回既有資料
        existed = _get_from_cache(session, slot_ts_utc, lat, lon)
        if existed:
            return existed
        else:
            raise
    return rec

def get_aqi_by_point_cached(session, lat: float, lon: float, force: bool = False) -> dict:
    now_utc = datetime.now(timezone.utc)
    slot_ts_utc = _floor_to_10min_utc(now_utc)

    # 1) 先查當前 slot
    cached = _get_from_cache(session, slot_ts_utc, lat, lon)
    if cached:
        return _as_payload(cached)

    # 2) 查這個 bucket 有沒有任何歷史紀錄
    latest = _get_latest_any_slot(session, lat, lon)

    # 3) 觸發抓取的條件：
    #    - force=True 明確要求
    #    - 正好整 10 分鐘
    #    - 完全沒有歷史紀錄（首查）
    if force or _is_exact_10min_boundary(now_utc) or latest is None:
        rec = _fetch_and_upsert(session, slot_ts_utc, lat, lon)
        return _as_payload(rec)

    # 4) 非邊界且已有歷史 → 回最近快取，不再打外部
    payload = _as_payload(latest)
    payload["note"] = "served_from_cache_recent_slot"
    return payload

def _as_payload(rec: AqiCache) -> Dict[str, Any]:
    return {
        "input": {"lat": rec.lat, "lon": rec.lon},
        "bucket": {"lat_bucket": float(rec.lat_bucket), "lon_bucket": float(rec.lon_bucket)},
        "grid_point": {"lat": rec.grid_lat, "lon": rec.grid_lon},
        "pm25_ugm3": round(rec.pm25_ugm3, 2),
        "slot_ts_utc": rec.slot_ts.isoformat(timespec="seconds"),
        "slot_ts_taipei": rec.slot_ts.astimezone(TW_TZ).isoformat(timespec="seconds"),
        "cams_reference_time": rec.cams_reference_time,
        "source": "CAMS global atmospheric composition forecasts (cached)",
    }
