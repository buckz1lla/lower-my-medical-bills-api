from datetime import datetime
import os

import stripe
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.analytics_routes import AnalyticsEvent, log_event_to_file
from app.store import (
    checkout_session_to_analysis,
    eob_analyses,
    mark_checkout_pending,
    mark_paid,
    payment_status_by_analysis,
)

router = APIRouter()


class CheckoutSessionRequest(BaseModel):
    analysis_id: str
    origin: str | None = None
    price_variant: str | None = None


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing required environment variable: {name}")
    return value


def _frontend_origin(request_origin: str | None) -> str:
    env_origin = os.getenv("FRONTEND_URL", "").strip()
    origin = request_origin or env_origin or "http://localhost:3000"
    return origin.rstrip("/")


def _configure_stripe() -> None:
    stripe.api_key = _require_env("STRIPE_SECRET_KEY")


def _extract_customer_email(session_obj: dict | object | None) -> str | None:
    if not session_obj:
        return None

    if isinstance(session_obj, dict):
        details = session_obj.get("customer_details", {}) or {}
        return details.get("email") or session_obj.get("customer_email")

    details = getattr(session_obj, "customer_details", None) or {}
    return details.get("email") if isinstance(details, dict) else getattr(session_obj, "customer_email", None)


def _log_payment_completed(
    analysis_id: str,
    amount_total: int | None,
    customer_email: str | None = None,
    price_variant: str | None = None,
) -> None:
    amount_dollars = round((amount_total or 299) / 100, 2)
    log_event_to_file(
        AnalyticsEvent(
            event="payment_completed",
            data={
                "analysisId": analysis_id,
                "amount": amount_dollars,
                "customer_email": customer_email,
                "price_variant": price_variant or "control",
            },
            timestamp=datetime.utcnow().isoformat(),
        )
    )


def _mark_paid_and_track(
    analysis_id: str,
    session_id: str | None = None,
    amount_total: int | None = None,
    customer_email: str | None = None,
    price_variant: str | None = None,
) -> dict:
    record, should_log = mark_paid(
        analysis_id,
        session_id=session_id,
        amount_total=amount_total,
        customer_email=customer_email,
        price_variant=price_variant,
    )
    if should_log:
        _log_payment_completed(analysis_id, amount_total, customer_email, price_variant)
    return record


def _price_id_for_variant(variant: str | None) -> tuple[str, str]:
    normalized = (variant or "control").strip().lower()
    if normalized not in {"control", "test"}:
        normalized = "control"

    if normalized == "test":
        test_price_id = os.getenv("STRIPE_PRICE_ID_TEST", "").strip()
        if test_price_id:
            return test_price_id, "test"

    control_price_id = os.getenv("STRIPE_PRICE_ID_CONTROL", "").strip() or _require_env("STRIPE_PRICE_ID")
    return control_price_id, "control"


@router.post("/payments/create-checkout-session")
async def create_checkout_session(payload: CheckoutSessionRequest):
    if payload.analysis_id not in eob_analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")

    _configure_stripe()
    price_id, variant = _price_id_for_variant(payload.price_variant)
    origin = _frontend_origin(payload.origin)

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{origin}/results/{payload.analysis_id}?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/results/{payload.analysis_id}?payment=cancelled",
            metadata={"analysis_id": payload.analysis_id, "price_variant": variant},
            payment_intent_data={"metadata": {"analysis_id": payload.analysis_id, "price_variant": variant}},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to create checkout session: {exc}")

    mark_checkout_pending(payload.analysis_id, session.id, variant)

    return {
        "session_id": session.id,
        "checkout_url": session.url,
        "price_variant": variant,
    }


@router.get("/payments/status/{analysis_id}")
async def get_payment_status(analysis_id: str, session_id: str | None = Query(None)):
    if analysis_id not in eob_analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")

    record = payment_status_by_analysis.get(analysis_id, {"status": "unpaid"})

    if record.get("status") != "paid" and session_id:
        _configure_stripe()
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            metadata = getattr(session, "metadata", {}) or {}
            if metadata.get("analysis_id") == analysis_id and getattr(session, "payment_status", None) == "paid":
                record = _mark_paid_and_track(
                    analysis_id,
                    session_id=session.id,
                    amount_total=getattr(session, "amount_total", None),
                    customer_email=_extract_customer_email(session),
                    price_variant=metadata.get("price_variant"),
                )
        except Exception:
            pass

    return {
        "analysis_id": analysis_id,
        "status": record.get("status", "unpaid"),
        "paid": record.get("status") == "paid",
        "checkout_session_id": record.get("checkout_session_id"),
        "paid_at": record.get("paid_at"),
        "customer_email": record.get("customer_email"),
        "price_variant": record.get("price_variant"),
    }


@router.post("/payments/webhook")
async def stripe_webhook(request: Request):
    _configure_stripe()
    webhook_secret = _require_env("STRIPE_WEBHOOK_SECRET")

    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=signature, secret=webhook_secret)
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook payload: {exc}")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {}) or {}
        analysis_id = metadata.get("analysis_id") or checkout_session_to_analysis.get(session.get("id"))
        if analysis_id:
            _mark_paid_and_track(
                analysis_id,
                session_id=session.get("id"),
                amount_total=session.get("amount_total"),
                customer_email=_extract_customer_email(session),
                price_variant=metadata.get("price_variant"),
            )

    return {"received": True}