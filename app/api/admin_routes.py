import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel

from app.security import OWNER_SESSION_COOKIE, issue_owner_session_token, is_owner_authenticated

router = APIRouter()

failed_attempts_by_ip = {}
locked_until_by_ip = {}


def _read_env_file_value(key: str) -> str:
    env_path = Path(__file__).resolve().parents[2] / ".env"
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


def _get_admin_dashboard_password() -> str:
    password = os.getenv("ADMIN_DASHBOARD_PASSWORD", "").strip()
    if password:
        return password
    return _read_env_file_value("ADMIN_DASHBOARD_PASSWORD")


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_login_limits() -> tuple[int, int]:
    max_attempts = int(os.getenv("ADMIN_LOGIN_MAX_ATTEMPTS", "5"))
    lockout_seconds = int(os.getenv("ADMIN_LOGIN_LOCKOUT_SECONDS", "900"))
    return max(1, max_attempts), max(30, lockout_seconds)


def _get_lockout_remaining_seconds(client_ip: str) -> int:
    locked_until = locked_until_by_ip.get(client_ip, 0)
    remaining = locked_until - int(time.time())
    return max(0, remaining)


def _record_failed_attempt(client_ip: str, max_attempts: int, lockout_seconds: int) -> int:
    failed_attempts_by_ip[client_ip] = failed_attempts_by_ip.get(client_ip, 0) + 1
    if failed_attempts_by_ip[client_ip] >= max_attempts:
        failed_attempts_by_ip[client_ip] = 0
        locked_until_by_ip[client_ip] = int(time.time()) + lockout_seconds
    return _get_lockout_remaining_seconds(client_ip)


def _clear_failed_attempts(client_ip: str) -> None:
    failed_attempts_by_ip.pop(client_ip, None)
    locked_until_by_ip.pop(client_ip, None)


class OwnerLoginRequest(BaseModel):
    password: str


@router.get("/admin/me")
async def admin_me(request: Request):
    return {"authenticated": is_owner_authenticated(request)}


@router.post("/admin/login")
async def admin_login(payload: OwnerLoginRequest, response: Response, request: Request):
    client_ip = _get_client_ip(request)
    max_attempts, lockout_seconds = _get_login_limits()

    remaining_lockout = _get_lockout_remaining_seconds(client_ip)
    if remaining_lockout > 0:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {remaining_lockout} seconds.",
        )

    expected_password = _get_admin_dashboard_password()
    if not expected_password:
        raise HTTPException(status_code=503, detail="Owner login is not configured")

    if payload.password != expected_password:
        remaining_lockout = _record_failed_attempt(client_ip, max_attempts, lockout_seconds)
        if remaining_lockout > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed attempts. Try again in {remaining_lockout} seconds.",
            )
        raise HTTPException(status_code=401, detail="Invalid password")

    _clear_failed_attempts(client_ip)

    try:
        token = issue_owner_session_token()
    except ValueError:
        raise HTTPException(status_code=503, detail="Owner session secret is not configured")

    secure_cookie = os.getenv("COOKIE_SECURE", "false").strip().lower() == "true"

    response.set_cookie(
        key=OWNER_SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=60 * 60 * 24,
        path="/",
    )

    return {"success": True}


@router.post("/admin/logout")
async def admin_logout(response: Response):
    response.delete_cookie(key=OWNER_SESSION_COOKIE, path="/")
    return {"success": True}
