# backend/services/aed_service.py
from typing import Any, Dict, List, Optional
import json
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from models import AedSite


def get_all_aeds_geojson(session: Session) -> Dict[str, Any]:
    """取得所有 AED 位置 (GeoJSON FeatureCollection)"""
    rows = session.execute(select(AedSite)).scalars().all()
    features = []
    for r in rows:
        if r.lon and r.lat:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [r.lon, r.lat]},
                "properties": {
                    "id": r.id,
                    "name": r.name,
                    "address": r.address,
                    "category": r.category,
                    "type": r.type,
                    "place": r.place,
                    "description": r.description
                }
            })
    return {"type": "FeatureCollection", "features": features}


def get_nearest_aed_geojson(session: Session, lat: float, lon: float, limit: int) -> Dict[str, Any]:
    """根據經緯度找出最近的 AED（回傳 GeoJSON FeatureCollection，features 由近到遠）。

    - `limit` 指定要取出的筆數（1..n）。
    - 若沒有資料，回傳空的 FeatureCollection。
    """
    pt = func.ST_SetSRID(func.ST_Point(lon, lat), 4326)

    q = (
        select(
            AedSite,
            func.ST_AsGeoJSON(AedSite.geom).label("geom_json"),
            func.ST_Distance(func.Geography(AedSite.geom), func.Geography(pt)).label("distance_m"),
        )
        .where(AedSite.geom.isnot(None))
        .order_by(func.ST_Distance(func.Geography(AedSite.geom), func.Geography(pt)))
        .limit(limit)
    )

    rows = session.execute(q).all()
    features: List[Dict[str, Any]] = []
    for row in rows:
        # row: (AedSite, geom_json, distance_m)
        site = row[0]
        geom_json = row[1]
        distance_m = float(row[2]) if row[2] is not None else None
        geometry = json.loads(geom_json) if geom_json else ( {"type": "Point", "coordinates": [site.lon, site.lat]} if site.lon and site.lat else None )
        props = {
            "id": site.id,
            "name": site.name,
            "address": site.address,
            "category": site.category,
            "type": site.type,
            "place": site.place,
            "description": site.description,
        }
        props["distance_m"] = distance_m
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": props,
        })

    return {"type": "FeatureCollection", "features": features}
