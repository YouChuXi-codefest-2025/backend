# backend/services/aqi_service.py
from __future__ import annotations
import os, tempfile
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple, Iterable

import cdsapi
import xarray as xr

DATASET = "cams-global-atmospheric-composition-forecasts"
TAIPEI_AREA = [25.3, 121.3, 24.9, 121.7]  # N, W, S, E
LEAD_HOURS = [0, 3, 6, 9, 12, 15, 18, 21, 24]
RUN_TIMES = ["00:00", "12:00"]
TW_TZ = timezone(timedelta(hours=8))


# ---------- Helper: 準備可嘗試的 reference time ----------
def _iter_latest_refs(now_utc: datetime) -> Iterable[Tuple[str, str]]:
    today = now_utc.date()
    yesterday = today - timedelta(days=1)
    for d in (today, yesterday):
        for t in reversed(RUN_TIMES):  # 12Z -> 00Z
            yield (str(d), t)


# ---------- Helper: 建立 Client ----------
def _build_cds_client() -> cdsapi.Client:
    url = os.getenv("CDS_API_URL", "https://ads.atmosphere.copernicus.eu/api")
    key = os.getenv("CDS_API_KEY")
    return cdsapi.Client(url=url, key=key, verify=1)


# ---------- Helper: 單位轉換 ----------
def _to_ug_per_m3(da: xr.DataArray) -> xr.DataArray:
    units = (da.attrs.get("units") or "").lower()
    if "kg" in units:
        da = da * 1e9  # kg/m³ → µg/m³
        da.attrs["units"] = "µg m-3"
    return da


# ---------- Helper: PM2.5 → AQI ----------
def _pm25_to_aqi(pm25: float) -> Tuple[int, str]:
    table = [
        (0.0, 12.0, 0, 50, "Good"),
        (12.1, 35.4, 51, 100, "Moderate"),
        (35.5, 55.4, 101, 150, "Unhealthy for Sensitive Groups"),
        (55.5, 150.4, 151, 200, "Unhealthy"),
        (150.5, 250.4, 201, 300, "Very Unhealthy"),
        (250.5, 500.4, 301, 500, "Hazardous"),
    ]
    c = max(0.0, min(pm25, 500.4))
    for c_low, c_high, i_low, i_high, cat in table:
        if c_low <= c <= c_high:
            aqi = round((i_high - i_low) / (c_high - c_low) * (c - c_low) + i_low)
            return aqi, cat
    return 500, "Hazardous"


# ---------- 主流程 ----------
def get_aqi_by_point(lat: float, lon: float) -> Dict[str, Any]:
    client = _build_cds_client()
    now_utc = datetime.now(timezone.utc)
    used_ref: Optional[str] = None

    with tempfile.TemporaryDirectory() as td:
        nc_path = os.path.join(td, "cams_pm25_latest.nc")

        # 依序嘗試最新的 12Z/00Z 組合
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
                client.retrieve(DATASET, req).download(nc_path)
                used_ref = f"{date_str} {time_str} UTC"
                break
            except Exception:
                continue

        if not used_ref:
            raise RuntimeError("❌ 無法取得最新 CAMS 資料")

        ds = xr.open_dataset(nc_path)
        var = "pm2p5"
        da = _to_ug_per_m3(ds[var])
        sub = da.sel(latitude=lat, longitude=lon, method="nearest")
        for dim in ("forecast_period", "forecast_reference_time", "valid_time"):
            if dim in sub.dims:
                sub = sub.mean(dim=dim)
        pm25 = float(sub.item())
        ds.close()

        aqi, category = _pm25_to_aqi(pm25)

        return {
            "input": {"lat": lat, "lon": lon},
            "pm25_ugm3": round(pm25, 2),
            "aqi": aqi,
            "category": category,
            "cams_reference_time": used_ref,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "generated_at_taipei": datetime.now(TW_TZ).isoformat(timespec="seconds"),
            "source": "CAMS global atmospheric composition forecasts",
        }
