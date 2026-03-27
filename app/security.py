import hashlib
import hmac
import os
import time
from pathlib import Path
from fastapi import Request

OWNER_SESSION_COOKIE = "owner_session"


def _read_env_file_value(key: str) -> str:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return ""

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        file_key, file_value = line.split("=", 1)
        if file_key.strip() == key:
            return file_value.strip().strip('"').strip("'")

    return ""


def _get_admin_session_secret() -> str:
    secret = os.getenv("ADMIN_SESSION_SECRET", "").strip()
    if secret:
        return secret
    return _read_env_file_value("ADMIN_SESSION_SECRET")


def issue_owner_session_token(ttl_seconds: int = 60 * 60 * 24) -> str:
    secret = _get_admin_session_secret()
    if not secret:
        raise ValueError("Missing ADMIN_SESSION_SECRET")

    expires_at = int(time.time()) + ttl_seconds
    payload = str(expires_at)
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify_owner_session_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False

    secret = _get_admin_session_secret()
    if not secret:
        return False

    payload, signature = token.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False

    try:
        expires_at = int(payload)
    except ValueError:
        return False

    return expires_at >= int(time.time())


def is_owner_authenticated(request: Request) -> bool:
    token = request.cookies.get(OWNER_SESSION_COOKIE)
    return verify_owner_session_token(token)
