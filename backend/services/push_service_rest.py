# backend/services/push_service_rest.py
import os, json, time
from typing import Dict, Any, List, Optional, Tuple
import requests

from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google.auth import default as google_auth_default

_FCM_SCOPE = ["https://www.googleapis.com/auth/firebase.messaging"]

# 簡單的 token 快取
_access_token: Tuple[str, float] | None = None  # (token, expires_at)

def _load_credentials():
    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if sa_json:
        info = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=_FCM_SCOPE)
    elif cred_path and os.path.exists(cred_path):
        creds = service_account.Credentials.from_service_account_file(cred_path, scopes=_FCM_SCOPE)
    else:
        # Application Default Credentials（Cloud Run 預設）
        creds, _ = google_auth_default(scopes=_FCM_SCOPE)
    return creds

def _get_access_token() -> str:
    global _access_token
    now = time.time()
    if _access_token and _access_token[1] - 60 > now:  # 提前 60 秒更新
        return _access_token[0]
    creds = _load_credentials()
    req = Request()
    creds.refresh(req)
    # google-auth 自帶 expiry；換算 epoch
    expires_at = getattr(creds, "expiry", None)
    ttl = 3000
    if expires_at:
        ttl = max(60, (expires_at.timestamp() - now))
    _access_token = (creds.token, now + ttl)
    return creds.token

def _endpoint() -> str:
    project_id = os.getenv("FCM_PROJECT_ID")
    if not project_id:
        raise RuntimeError("FCM_PROJECT_ID not set")
    return f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

def _do_send(payload: Dict[str, Any]) -> Dict[str, Any]:
    token = _get_access_token()
    r = requests.post(
        _endpoint(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"message": payload},
        timeout=10,
    )
    if r.status_code == 200:
        return {"success": True, "message": r.json().get("name")}
    # 解析錯誤，回傳可讀資訊
    try:
        err = r.json()
    except Exception:
        err = {"raw": r.text}
    return {"success": False, "status": r.status_code, "error": err}

# ---- 封裝對外 API（與原路由相容） ----

def send_to_token(token: str, title: str, body: str, data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    payload = {
        "token": token,
        "notification": {"title": title, "body": body},
        "data": data or {},
    }
    return _do_send(payload)

def send_to_topic(topic: str, title: str, body: str, data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    payload = {
        "topic": topic,
        "notification": {"title": title, "body": body},
        "data": data or {},
    }
    return _do_send(payload)

def send_multicast(tokens: List[str], title: str, body: str, data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    # FCM v1 沒有單一「群發」JSON；這裡逐一送（也可自己做平行或批次）
    ok, fail = 0, 0
    errors: List[Dict[str, Any]] = []
    for t in tokens:
        res = send_to_token(t, title, body, data)
        if res.get("success"):
            ok += 1
        else:
            fail += 1
            errors.append({"token": t, "error": res.get("error"), "status": res.get("status")})
    return {"success": True, "success_count": ok, "failure_count": fail, "errors": errors}
