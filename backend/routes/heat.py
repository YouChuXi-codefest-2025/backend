# backend/routes/heat_forecast.py
from flask import Blueprint, request, jsonify
from werkzeug.exceptions import BadRequest
from db import SessionLocal
from services.heat_service import get_heat_forecast_by_point

bp = Blueprint("heat_forecast", __name__)

@bp.get("/heat/forecast")
def heat_forecast():
    """根據使用者經緯度，回傳所在區的未來所有熱傷害指數預報"""
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except Exception:
        raise BadRequest("lat/lon required")

    session = SessionLocal()
    try:
        result = get_heat_forecast_by_point(session, lat=lat, lon=lon)
        if not result:
            return jsonify({"note": "no data"}), 200
        return jsonify(result), 200
    finally:
        session.close()
