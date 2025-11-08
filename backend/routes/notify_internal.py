from flask import Blueprint, request, jsonify
from werkzeug.exceptions import BadRequest, Unauthorized
from sqlalchemy import select
import os, json
from db import SessionLocal
from models import DeviceToken
from services.push_service_rest import (
    send_to_token, send_to_topic, send_multicast
)

bp = Blueprint("notify_internal", __name__)

# 簡單 API Key 保護（建議改成更嚴謹的 IAM / IAP）
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

def _check_auth(req):
    if not INTERNAL_API_KEY:
        return  # 未配置就不檢查（開發用）；正式環境請一定要設
    key = req.headers.get("X-API-Key")
    if key != INTERNAL_API_KEY:
        raise Unauthorized("invalid api key")

@bp.post("/internal/notify")
def internal_notify():
    _check_auth(request)
    js = request.get_json(silent=True) or {}
    title = js.get("title") or "通知"
    body = js.get("body") or ""
    data = js.get("data") or {}
    token = js.get("token")
    topic = js.get("topic")
    user_id = js.get("user_id")
    tokens = js.get("tokens")  # 可傳陣列

    if topic:
        return jsonify(send_to_topic(topic, title, body, data))

    if token:
        return jsonify(send_to_token(token, title, body, data))

    if tokens and isinstance(tokens, list):
        return jsonify(send_multicast(tokens, title, body, data))

    if user_id:
        # 發送給某個 user_id 所有裝置
        s = SessionLocal()
        try:
            ts = [t.fcm_token for t in s.execute(
                select(DeviceToken).where(DeviceToken.user_id == user_id)
            ).scalars().all()]
        finally:
            s.close()
        if not ts:
            return jsonify({"success": False, "reason": "no tokens for user"}), 404
        return jsonify(send_multicast(ts, title, body, data))

    raise BadRequest("need one of: token | tokens[] | topic | user_id")
