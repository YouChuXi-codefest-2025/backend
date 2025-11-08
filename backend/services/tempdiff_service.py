# backend/services/tempdiff_service.py
import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import select, func
from models import TaipeiDistrict

CWA_API = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0085-005"
CWA_API_KEY = os.getenv("CWA_API_KEY")
TW_TZ = timezone(timedelta(hours=8))

def _normalize(s: str) -> str:
    return (s or "").strip()

def _parse_iso8601(s: str) -> datetime:
    # e.g. "2025-11-10T21:00:00+08:00"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        # 後備：把空白版轉回 iso
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TW_TZ)
        except Exception:
            return datetime.max.replace(tzinfo=TW_TZ)

def get_district_by_point(session: Session, lat: float, lon: float) -> Optional[str]:
    """用 PostGIS 判斷行政區（先 contains，再 50m 容錯，最後 KNN）。"""
    pt = func.ST_SetSRID(func.ST_Point(lon, lat), 4326)

    q1 = select(TaipeiDistrict.district_name).where(func.ST_Contains(TaipeiDistrict.geom, pt)).limit(1)
    hit = session.execute(q1).scalar_one_or_none()
    if hit:
        return hit

    q2 = (
        select(TaipeiDistrict.district_name)
        .where(func.ST_DWithin(func.Geography(TaipeiDistrict.geom), func.Geography(pt), 50.0))
        .order_by(func.ST_Distance(func.Geography(TaipeiDistrict.geom), func.Geography(pt)))
        .limit(1)
    )
    near = session.execute(q2).scalar_one_or_none()
    if near:
        return near

    q3 = select(TaipeiDistrict.district_name).order_by(TaipeiDistrict.geom.op("<->")(pt)).limit(1)
    return session.execute(q3).scalar_one_or_none()

def fetch_tempdiff_forecast_for_town(town_name: str) -> Optional[Dict[str, Any]]:
    """
    取得「健康氣象溫差提醒指數」該行政區所有時段，並以 IssueTime 排序。
    回傳:
    {
      city, district,
      forecasts: [{issue_time, start_time, end_time, temperature_difference_index, temperature_difference_warning}]
    }
    """
    if not CWA_API_KEY:
        raise RuntimeError("CWA_API_KEY is not set")

    params = {
        "Authorization": CWA_API_KEY,
        "format": "JSON",
        "CountyName": "臺北市",
    }
    r = requests.get(CWA_API, params=params, timeout=10)
    r.raise_for_status()
    data = r.json() or {}

    records = data.get("records", {}) or {}
    locations = records.get("Locations", []) or []
    city_block = None
    for loc in locations:
        if _normalize(loc.get("CountyName")) == "臺北市":
            city_block = loc
            break
    if not city_block:
        return None

    target = _normalize(town_name)
    for item in city_block.get("Location", []) or []:
        if _normalize(item.get("TownName")) == target:
            out: List[Dict[str, Any]] = []
            for t in item.get("Time", []) or []:
                we = t.get("WeatherElements", {}) or {}
                out.append({
                    "issue_time": t.get("IssueTime"),  # ISO8601(+08:00)
                    "start_time": t.get("StartTime"),  # 有些批次也會帶 Start/End
                    "end_time": t.get("EndTime"),
                    "temperature_difference_index": we.get("TemperatureDifferenceIndex"),
                    "temperature_difference_warning": we.get("TemperatureDifferenceWarning", "")
                })
            # 依 IssueTime 排序
            out.sort(key=lambda x: _parse_iso8601(x["issue_time"]) if x.get("issue_time") else datetime.max.replace(tzinfo=TW_TZ))
            return {
                "city": "臺北市",
                "district": target,
                "forecasts": out
            }
    return None

def get_tempdiff_forecast_by_point(session: Session, lat: float, lon: float) -> Optional[Dict[str, Any]]:
    district = get_district_by_point(session, lat, lon)
    if not district:
        return None
    return fetch_tempdiff_forecast_for_town(district)
