# backend/routes/aed_sites.py
from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest
from db import SessionLocal
from services.aed_service import get_all_aeds_geojson, get_nearest_aed_geojson

bp = Blueprint("aed_sites", __name__)

@bp.get("/aeds")
def get_all_aeds():
    """取得所有 AED 位置 (GeoJSON)"""
    s = SessionLocal()
    try:
        data = get_all_aeds_geojson(s)
        return jsonify(data), 200
    finally:
        s.close()


@bp.get("/aeds/nearest")
def get_nearest_aed():
    """依經緯度找最近的 AED (GeoJSON)"""
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except Exception:
        raise BadRequest("lat/lon required")

    try:
        limit = int(request.args.get("limit", 1))
        if limit <= 0 or limit > 100:
            raise ValueError()
    except Exception:
        raise BadRequest("invalid limit (must be 1-100)")

    s = SessionLocal()
    try:
        item = get_nearest_aed_geojson(s, lat=lat, lon=lon, limit=limit)
        if not item:
            return jsonify({"note": "no data"}), 200
        return jsonify(item), 200
    finally:
        s.close()
