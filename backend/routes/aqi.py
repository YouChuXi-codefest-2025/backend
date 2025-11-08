from flask import Blueprint, request, jsonify
from werkzeug.exceptions import BadRequest
from services.aqi_service import get_aqi_by_point

bp = Blueprint("aqi", __name__)

@bp.get("/aqi/pm25")
def get_pm25_aqi():
    """取得指定經緯度的即時 PM2.5 與 AQI"""
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except Exception:
        raise BadRequest("lat/lon required")

    try:
        result = get_aqi_by_point(lat, lon)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 502
