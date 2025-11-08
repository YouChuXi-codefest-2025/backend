# backend/routes/cooling_sites.py
from flask import Blueprint, request, Response
from werkzeug.exceptions import BadRequest
import json
from db import SessionLocal
from services.cooling_sites_service import (
    list_cooling_sites_geojson,
    nearest_cooling_site_geojson,
)

bp = Blueprint("cooling_sites", __name__)

@bp.get("/sites")
def get_sites():
    try:
        limit = int(request.args.get("limit", 600))
        offset = int(request.args.get("offset", 0))
        if limit <= 0 or limit > 1000 or offset < 0:
            raise ValueError()
    except Exception:
        raise BadRequest("invalid limit/offset")

    session = SessionLocal()
    try:
        fc = list_cooling_sites_geojson(session, limit=limit, offset=offset)
        return Response(json.dumps(fc, ensure_ascii=False), mimetype="application/geo+json")
    finally:
        session.close()

@bp.get("/sites/nearest")
def get_nearest_site():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except Exception:
        raise BadRequest("lat/lon required")

    try:
        r = request.args.get("r")
        radius_m = float(r) if r is not None else 1000.0
        if radius_m <= 0:
            raise ValueError()
    except Exception:
        raise BadRequest("invalid r (radius meters)")

    session = SessionLocal()
    try:
        fc = nearest_cooling_site_geojson(session, lat=lat, lon=lon, radius_m=radius_m)
        return Response(json.dumps(fc, ensure_ascii=False), mimetype="application/geo+json")
    finally:
        session.close()
