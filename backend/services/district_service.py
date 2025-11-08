# backend/services/district_service.py
from sqlalchemy import select, func, text
from models import TaipeiDistrict

def resolve_district(session, lat: float, lon: float) -> dict | None:
    """
    回傳：
      {"city": ..., "district": ..., "method": "..."} 或 None
    查詢邏輯：
      1) ST_Contains
      2) 50m 內最近（geography 距離）
      3) KNN (<->) 最近
    """
    # 1) 嚴格包含
    q_contains = (
        select(TaipeiDistrict.city_name, TaipeiDistrict.district_name)
        .where(
            func.ST_Contains(
                TaipeiDistrict.geom,
                func.ST_SetSRID(func.ST_Point(lon, lat), 4326)
            )
        )
        .limit(1)
    )
    hit = session.execute(q_contains).first()
    if hit:
        return {"city": hit.city_name, "district": hit.district_name, "method": "contains"}

    # 2) 邊界容錯（50m 內最近）
    q_near = (
        select(TaipeiDistrict.city_name, TaipeiDistrict.district_name)
        .where(
            func.ST_DWithin(
                func.Geography(TaipeiDistrict.geom),
                func.Geography(func.ST_SetSRID(func.ST_Point(lon, lat), 4326)),
                50.0
            )
        )
        .order_by(
            func.ST_Distance(
                func.Geography(TaipeiDistrict.geom),
                func.Geography(func.ST_SetSRID(func.ST_Point(lon, lat), 4326))
            )
        )
        .limit(1)
    )
    near = session.execute(q_near).first()
    if near:
        return {"city": near.city_name, "district": near.district_name, "method": "nearest<50m"}

    # 3) KNN 最近（使用 ORM 的 .op("<->")，避免文字參數冒號錯誤）
    q_knn = (
        select(TaipeiDistrict.city_name, TaipeiDistrict.district_name)
        .order_by(
            TaipeiDistrict.geom.op("<->")(func.ST_SetSRID(func.ST_Point(lon, lat), 4326))
        )
        .limit(1)
    )
    nn = session.execute(q_knn).first()
    if nn:
        return {"city": nn.city_name, "district": nn.district_name, "method": "knn"}

    return None
