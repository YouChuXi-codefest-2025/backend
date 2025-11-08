# backend/routes/districts.py
from flask import Blueprint, request, jsonify
from werkzeug.exceptions import BadRequest
from db import SessionLocal
from services.district_service import resolve_district

bp = Blueprint("districts", __name__)

@bp.get("/which-district")
def which_district():
    # 1) 解析參數
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except Exception:
        raise BadRequest("lat/lon required")

    # 2) 交給 service 做商業邏輯
    session = SessionLocal()
    try:
        result = resolve_district(session, lat, lon)
        if not result:
            return jsonify(city="臺北市", district=None, note="not in polygon / too far"), 200
        return jsonify(result), 200
    finally:
        # 若使用 scoped_session，這裡可省；保守起見還是關一下
        try:
            session.close()
        except Exception:
            pass
