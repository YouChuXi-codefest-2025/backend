# backend/services/cooling_site_service.py
from typing import List, Dict, Any
import json
from sqlalchemy import select, func
from models import CoolingSite

def _row_to_feature(row, include_distance: bool = False) -> Dict[str, Any]:
    """
    row: (CoolingSite, geom_json, [distance_m])
    產出 GeoJSON Feature（符合 RFC 7946，不含 crs）
    """
    site = row[0]
    geom_json = row[1]
    geometry = json.loads(geom_json) if geom_json else None

    props = {
        "id": site.id,
        "location_type": site.location_type,
        "name": site.name,
        "district_name": site.district_name,
        "address": site.address,
        "lon": site.lon,
        "lat": site.lat,
        "phone": site.phone,
        "ext": site.ext,
        "mobile": site.mobile,
        "other_contact": site.other_contact,
        "open_hours": site.open_hours,
        "fan": site.fan,
        "ac": site.ac,
        "toilet": site.toilet,
        "seating": site.seating,
        "drinking": site.drinking,
        "accessible_seat": site.accessible_seat,
        "features": site.features,
        "notes": site.notes,
    }
    if include_distance:
        props["distance_m"] = float(row[2]) if row[2] is not None else None

    return {
        "type": "Feature",
        "id": site.id,           # 可選；有效 JSON 值即可
        "geometry": geometry,    # 可能為 null（允許）
        "properties": props,
    }

def list_cooling_sites_geojson(session, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    q = (
        select(
            CoolingSite,
            func.ST_AsGeoJSON(CoolingSite.geom).label("geom_json"),
        )
        .order_by(CoolingSite.id.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = session.execute(q).all()
    features = [_row_to_feature(r, include_distance=False) for r in rows]
    return {"type": "FeatureCollection", "features": features}

def nearest_cooling_site_geojson(session, lat: float, lon: float, radius_m: float = 1000.0) -> Dict[str, Any]:
    pt = func.ST_SetSRID(func.ST_Point(lon, lat), 4326)

    # 先在半徑內找最近（真實距離）
    q_within = (
        select(
            CoolingSite,
            func.ST_AsGeoJSON(CoolingSite.geom).label("geom_json"),
            func.ST_Distance(func.Geography(CoolingSite.geom), func.Geography(pt)).label("distance_m"),
        )
        .where(
            CoolingSite.geom.isnot(None),
            func.ST_DWithin(func.Geography(CoolingSite.geom), func.Geography(pt), radius_m),
        )
        .order_by(func.ST_Distance(func.Geography(CoolingSite.geom), func.Geography(pt)))
        .limit(1)
    )
    res = session.execute(q_within).first()
    if res:
        return {"type": "FeatureCollection", "features": [_row_to_feature(res, include_distance=True)]}

    # 半徑內沒有 → 退回全域最近（KNN）再計距離
    q_knn = (
        select(
            CoolingSite,
            func.ST_AsGeoJSON(CoolingSite.geom).label("geom_json"),
            func.ST_Distance(func.Geography(CoolingSite.geom), func.Geography(pt)).label("distance_m"),
        )
        .where(CoolingSite.geom.isnot(None))
        .order_by(CoolingSite.geom.op("<->")(pt))
        .limit(1)
    )
    res2 = session.execute(q_knn).first()
    if res2:
        return {"type": "FeatureCollection", "features": [_row_to_feature(res2, include_distance=True)]}

    # 沒資料：回空集合（符合規格）
    return {"type": "FeatureCollection", "features": []}
