# backend/services/heat_service.py
import os, requests
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from models import TaipeiDistrict

CWA_API = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/M-A0085-001"
CWA_API_KEY = os.getenv("CWA_API_KEY")
TW_TZ = timezone(timedelta(hours=8))


def get_district_by_point(session: Session, lat: float, lon: float) -> Optional[str]:
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


def fetch_heat_forecast_for_town(town_name: str) -> Optional[Dict[str, Any]]:
    """取得該行政區所有未來時間預報（已依 issue_time 排序）"""
    if not CWA_API_KEY:
        raise RuntimeError("CWA_API_KEY not set")

    params = {"Authorization": CWA_API_KEY, "CountyName": "臺北市"}
    resp = requests.get(CWA_API, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    records = data.get("records", {})
    locations = records.get("Locations", [])
    for loc in locations:
        if loc.get("CountyName") == "臺北市":
            for sub in loc.get("Location", []):
                if sub.get("TownName") == town_name:
                    result = []
                    for t in sub.get("Time", []):
                        we = t.get("WeatherElements", {}) or {}
                        result.append({
                            "issue_time": t.get("IssueTime"),
                            "heat_injury_index": we.get("HeatInjuryIndex"),
                            "heat_injury_warning": we.get("HeatInjuryWarning", "")
                        })

                    # ✅ 在這裡排序：由早到晚
                    def _parse_time(x):
                        try:
                            return datetime.strptime(x["issue_time"], "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            return datetime.max
                    result.sort(key=_parse_time)

                    return {
                        "city": "臺北市",
                        "district": town_name,
                        "forecasts": result
                    }
    return None


def get_heat_forecast_by_point(session: Session, lat: float, lon: float) -> Optional[Dict[str, Any]]:
    district = get_district_by_point(session, lat, lon)
    if not district:
        return None
    return fetch_heat_forecast_for_town(district)
