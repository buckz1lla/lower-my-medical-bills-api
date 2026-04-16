from datetime import datetime
import json
from pathlib import Path
from typing import Optional


eob_analyses = {}
payment_status_by_analysis = {}
checkout_session_to_analysis = {}
processed_webhook_events = {}  # Track processed webhook IDs for idempotency
refund_records = {}  # Track refunds by analysis_id
failed_payment_attempts = {}  # Track failed payment attempts for retry logic

_STORE_FILE = Path(__file__).parent.parent / "data" / "payment_state.json"


def _save_payment_state() -> None:
    _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "payment_status_by_analysis": payment_status_by_analysis,
        "checkout_session_to_analysis": checkout_session_to_analysis,
        "processed_webhook_events": processed_webhook_events,
        "refund_records": refund_records,
        "failed_payment_attempts": failed_payment_attempts,
        "updated_at": datetime.utcnow().isoformat(),
    }
    with open(_STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


def _load_payment_state() -> None:
    if not _STORE_FILE.exists():
        return

    try:
        with open(_STORE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        payment_status_by_analysis.update(payload.get("payment_status_by_analysis", {}))
        checkout_session_to_analysis.update(payload.get("checkout_session_to_analysis", {}))
        processed_webhook_events.update(payload.get("processed_webhook_events", {}))
        refund_records.update(payload.get("refund_records", {}))
        failed_payment_attempts.update(payload.get("failed_payment_attempts", {}))
    except Exception as e:
        # Keep startup resilient; file can be recreated on next successful update.
        print(f"Warning: Failed to load payment state: {e}")
        return


def initialize_analysis_payment(analysis_id: str) -> None:
    payment_status_by_analysis.setdefault(
        analysis_id,
        {
            "status": "unpaid",
            "updated_at": datetime.utcnow().isoformat(),
        },
    )
    _save_payment_state()


def mark_checkout_pending(analysis_id: str, session_id: str, price_variant: str | None = None) -> dict:
    record = {
        "status": "pending",
        "checkout_session_id": session_id,
        "price_variant": price_variant,
        "updated_at": datetime.utcnow().isoformat(),
    }
    payment_status_by_analysis[analysis_id] = record
    checkout_session_to_analysis[session_id] = analysis_id
    _save_payment_state()
    return record


def mark_paid(
    analysis_id: str,
    session_id: str | None = None,
    amount_total: int | None = None,
    customer_email: str | None = None,
    price_variant: str | None = None,
) -> tuple[dict, bool]:
    existing = payment_status_by_analysis.get(analysis_id, {})
    was_paid = existing.get("status") == "paid"
    record = {
        **existing,
        "status": "paid",
        "checkout_session_id": session_id or existing.get("checkout_session_id"),
        "amount_total": amount_total if amount_total is not None else existing.get("amount_total"),
        "customer_email": customer_email or existing.get("customer_email"),
        "price_variant": price_variant or existing.get("price_variant"),
        "paid_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    payment_status_by_analysis[analysis_id] = record
    if session_id:
        checkout_session_to_analysis[session_id] = analysis_id
    _save_payment_state()
    return record, not was_paid


def record_webhook_event(event_id: str) -> bool:
    """Track processed webhook ID for idempotency. Returns True if new, False if already processed."""
    if event_id in processed_webhook_events:
        return False
    processed_webhook_events[event_id] = {
        "processed_at": datetime.utcnow().isoformat()
    }
    _save_payment_state()
    return True


def record_refund(
    analysis_id: str,
    refund_amount: int,
    reason: str,
    stripe_refund_id: str | None = None,
) -> dict:
    """Record a refund for an analysis."""
    if analysis_id not in refund_records:
        refund_records[analysis_id] = []
    
    refund_record = {
        "refund_id": stripe_refund_id or f"refund_{analysis_id}_{datetime.utcnow().timestamp()}",
        "amount": refund_amount,
        "reason": reason,
        "created_at": datetime.utcnow().isoformat(),
    }
    refund_records[analysis_id].append(refund_record)
    _save_payment_state()
    return refund_record


def get_refund_history(analysis_id: str) -> list[dict]:
    """Get all refunds for an analysis."""
    return refund_records.get(analysis_id, [])


def record_failed_payment_attempt(
    analysis_id: str,
    error: str,
    error_code: str | None = None,
) -> dict:
    """Record a failed payment attempt for retry logic."""
    if analysis_id not in failed_payment_attempts:
        failed_payment_attempts[analysis_id] = []
    
    attempt = {
        "attempted_at": datetime.utcnow().isoformat(),
        "error": error,
        "error_code": error_code,
        "retry_count": len(failed_payment_attempts[analysis_id]) + 1,
    }
    failed_payment_attempts[analysis_id].append(attempt)
    _save_payment_state()
    return attempt


def get_payment_history(analysis_id: str) -> dict:
    """Get complete payment history for an analysis."""
    return {
        "current_status": payment_status_by_analysis.get(analysis_id, {}),
        "refunds": refund_records.get(analysis_id, []),
        "failed_attempts": failed_payment_attempts.get(analysis_id, []),
    }


_load_payment_state()