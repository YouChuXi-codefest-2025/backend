from flask import Blueprint, request, jsonify
from werkzeug.exceptions import BadRequest
from services.aqi_service import get_aqi_by_point_cached
from db import SessionLocal

bp = Blueprint("aqi", __name__)

@bp.get("/aqi/pm25")
def aqi_pm25():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except Exception:
        raise BadRequest("lat/lon required")

    s = SessionLocal()
    try:
        result = get_aqi_by_point_cached(s, lat, lon)
        status = 200 if "error" not in result else 503
        return jsonify(result), status
    finally:
        s.close()
