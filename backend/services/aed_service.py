# backend/services/aed_service.py
from typing import Any, Dict, List, Optional
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


def get_nearest_aed_geojson(session: Session, lat: float, lon: float, limit:int) -> Optional[Dict[str, Any]]:
    """根據經緯度找出最近 AED"""
    pt = func.ST_SetSRID(func.ST_Point(lon, lat), 4326)
    q = (
        select(AedSite)
        .order_by(AedSite.geom.op("<->")(pt))
        .limit(limit)
    )
    nearest = session.execute(q).all()
    if not nearest:
        return None
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [nearest.lon, nearest.lat]},
        "properties": {
            "id": nearest.id,
            "name": nearest.name,
            "address": nearest.address,
            "category": nearest.category,
            "type": nearest.type,
            "place": nearest.place,
            "description": nearest.description
        }
    }
