from datetime import datetime
import json
from pathlib import Path


eob_analyses = {}
payment_status_by_analysis = {}
checkout_session_to_analysis = {}

_STORE_FILE = Path(__file__).parent.parent / "data" / "payment_state.json"


def _save_payment_state() -> None:
    _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "payment_status_by_analysis": payment_status_by_analysis,
        "checkout_session_to_analysis": checkout_session_to_analysis,
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
    except Exception:
        # Keep startup resilient; file can be recreated on next successful update.
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


_load_payment_state()