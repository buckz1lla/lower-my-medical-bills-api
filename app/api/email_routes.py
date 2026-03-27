from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
import os
from app.security import is_owner_authenticated
from app.services.email_service import (
    subscribe_email,
    get_all_subscribers,
    get_signup_counts_by_day,
    send_reminder_emails,
)

router = APIRouter()


def _require_owner_or_api_key(request: Request, api_key: Optional[str]) -> None:
    expected = os.getenv("ANALYTICS_API_KEY", "").strip()
    if is_owner_authenticated(request):
        return
    if expected and api_key == expected:
        return
    raise HTTPException(status_code=401, detail="Owner authentication required.")


class EmailSubscribeRequest(BaseModel):
    email: str
    analysis_id: str
    savings_amount: Optional[float] = 0.0


def _validate_email(email: str) -> bool:
    """Minimal structural validation — no external deps."""
    email = email.strip()
    if not email or "@" not in email:
        return False
    parts = email.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts
    if not local or not domain or "." not in domain:
        return False
    # Domain must have a non-empty TLD
    tld = domain.rsplit(".", 1)[-1]
    return len(tld) >= 2


@router.post("/email/subscribe")
async def subscribe(req: EmailSubscribeRequest):
    """Subscribe an email for reminder emails. Open endpoint — no auth required."""
    email = req.email.strip().lower()
    if not _validate_email(email):
        raise HTTPException(status_code=422, detail="Invalid email address.")

    if not req.analysis_id or not req.analysis_id.strip():
        raise HTTPException(status_code=422, detail="analysis_id is required.")

    result = subscribe_email(
        email=email,
        analysis_id=req.analysis_id.strip(),
        savings_amount=req.savings_amount or 0.0,
    )
    return {"ok": True, "is_new": result["is_new"]}


@router.get("/email/subscribers")
async def list_subscribers(request: Request, api_key: Optional[str] = Query(None)):
    """List all email subscribers. Owner authentication required."""
    _require_owner_or_api_key(request, api_key)

    subscribers = get_all_subscribers()
    return {"count": len(subscribers), "subscribers": subscribers}


@router.get("/analytics/email-signups")
async def email_signup_analytics(
    request: Request,
    days: int = 7,
    api_key: Optional[str] = Query(None),
):
    """Return email signup analytics. Owner authentication required."""
    _require_owner_or_api_key(request, api_key)

    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days must be between 1 and 90.")

    daily = get_signup_counts_by_day(days=days)
    all_subscribers = get_all_subscribers()
    period_total = sum(d["signups"] for d in daily)

    return {
        "total_subscribers": len(all_subscribers),
        "period_signups": period_total,
        "days": days,
        "daily": daily,
    }


@router.post("/email/send-reminders")
async def send_reminders(request: Request, api_key: Optional[str] = Query(None)):
    """Send reminder emails to all subscribers. Owner authentication required."""
    _require_owner_or_api_key(request, api_key)

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    result = send_reminder_emails(frontend_url=frontend_url)

    # If SMTP isn't configured and nothing was sent, surface a clear message
    if "error" in result and result.get("sent", 0) == 0:
        raise HTTPException(status_code=503, detail=result["error"])

    return result
