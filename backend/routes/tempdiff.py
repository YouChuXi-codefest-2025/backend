# backend/routes/tempdiff.py
from flask import Blueprint, request, jsonify
from werkzeug.exceptions import BadRequest
from db import SessionLocal
from datetime import datetime, timezone, timedelta
from services.tempdiff_service import get_tempdiff_forecast_by_point

bp = Blueprint("tempdiff", __name__)

@bp.get("/tempdiff/forecast")
def tempdiff_forecast():
    """
    依前端 lat/lon 判斷行政區，回傳該區 F-A0085-005 溫差提醒指數（依 IssueTime 排序）
    """
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except Exception:
        raise BadRequest("lat/lon required")

    session = SessionLocal()
    try:
        result = get_tempdiff_forecast_by_point(session, lat=lat, lon=lon)
        if not result:
            return jsonify({"note": "no data"}), 200
        return jsonify(result), 200
    finally:
        try:
            session.close()
        except Exception:
            pass
