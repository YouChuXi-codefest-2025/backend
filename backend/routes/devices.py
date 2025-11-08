from flask import Blueprint, request, jsonify
from werkzeug.exceptions import BadRequest
from sqlalchemy import select
from db import SessionLocal
from models import DeviceToken

bp = Blueprint("devices", __name__)

@bp.post("/devices/register")
def register_device():
    js = request.get_json(silent=True) or {}
    token = js.get("fcm_token")
    if not token:
        raise BadRequest("fcm_token required")
    user_id = js.get("user_id")
    platform = js.get("platform")

    s = SessionLocal()
    try:
        # upsert 簡版：存在就更新 user/platform；不存在就新增
        existing = s.execute(select(DeviceToken).where(DeviceToken.fcm_token == token)).scalar_one_or_none()
        if existing:
            existing.user_id = user_id
            existing.platform = platform
        else:
            s.add(DeviceToken(fcm_token=token, user_id=user_id, platform=platform))
        s.commit()
        return jsonify({"ok": True})
    finally:
        s.close()
