from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from typing import Optional


# How long a parsed analysis (which contains PHI: provider names, service
# descriptions, dates, amounts) is retained before it is automatically purged
# from memory and disk. Bounding retention minimizes the sensitive data we hold.
# Raw uploaded file bytes are never persisted — only an irreversible SHA-256 hash.
try:
    ANALYSIS_RETENTION_HOURS = max(1, int(os.getenv("ANALYSIS_RETENTION_HOURS", "24")))
except (TypeError, ValueError):
    ANALYSIS_RETENTION_HOURS = 24

eob_analyses = {}
analysis_created_at: dict[str, str] = {}  # analysis_id -> ISO timestamp of creation
payment_status_by_analysis = {}
checkout_session_to_analysis = {}
processed_webhook_events = {}  # Track processed webhook IDs for idempotency
refund_records = {}  # Track refunds by analysis_id
failed_payment_attempts = {}  # Track failed payment attempts for retry logic
paid_analysis_by_hash: dict[str, str] = {}  # file_hash -> analysis_id that was paid

# Outcome store: {analysis_id: {opportunity_id: {outcome dict}}}
# Persisted to data/outcome_state.json independently of payment state.
outcome_store: dict[str, dict[str, dict]] = {}

_STORE_FILE = Path(__file__).parent.parent / "data" / "payment_state.json"
_OUTCOME_FILE = Path(__file__).parent.parent / "data" / "outcome_state.json"
_ANALYSIS_FILE = Path(__file__).parent.parent / "data" / "analysis_state.json"


def _save_payment_state() -> None:
    _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "payment_status_by_analysis": payment_status_by_analysis,
        "checkout_session_to_analysis": checkout_session_to_analysis,
        "processed_webhook_events": processed_webhook_events,
        "refund_records": refund_records,
        "failed_payment_attempts": failed_payment_attempts,
        "paid_analysis_by_hash": paid_analysis_by_hash,
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
        paid_analysis_by_hash.update(payload.get("paid_analysis_by_hash", {}))
    except Exception as e:
        # Keep startup resilient; file can be recreated on next successful update.
        print(f"Warning: Failed to load payment state: {e}")
        return


# ===== OUTCOME PERSISTENCE =====

def _save_outcome_state() -> None:
    _OUTCOME_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUTCOME_FILE, "w", encoding="utf-8") as f:
        json.dump({"outcomes": outcome_store, "updated_at": datetime.utcnow().isoformat()}, f, ensure_ascii=True, indent=2)


def _load_outcome_state() -> None:
    if not _OUTCOME_FILE.exists():
        return
    try:
        with open(_OUTCOME_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        outcome_store.update(payload.get("outcomes", {}))
    except Exception as e:
        print(f"Warning: Failed to load outcome state: {e}")


def upsert_outcome(analysis_id: str, opportunity_id: str, outcome_dict: dict) -> list[dict]:
    """Insert or overwrite a single outcome record. Returns all outcomes for the analysis."""
    outcome_store.setdefault(analysis_id, {})[opportunity_id] = outcome_dict
    _save_outcome_state()
    return list(outcome_store[analysis_id].values())


def get_outcomes(analysis_id: str) -> list[dict]:
    """Return all recorded outcomes for an analysis (empty list if none)."""
    return list(outcome_store.get(analysis_id, {}).values())


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
    # Index by file hash so re-uploads of the same file are recognized as paid
    analysis = eob_analyses.get(analysis_id)
    if analysis and getattr(analysis, "file_hash", None):
        paid_analysis_by_hash[analysis.file_hash] = analysis_id
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


def get_paid_analysis_id_for_hash(file_hash: str) -> Optional[str]:
    """Return the analysis_id of a previously paid analysis with the same file hash, or None."""
    return paid_analysis_by_hash.get(file_hash)


# ===== ANALYSIS PERSISTENCE =====

def _save_analysis_state() -> None:
    _ANALYSIS_FILE.parent.mkdir(parents=True, exist_ok=True)
    serializable = {}
    for aid, analysis in eob_analyses.items():
        try:
            serializable[aid] = analysis.model_dump(mode="json")
        except Exception:
            pass
    with open(_ANALYSIS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "analyses": serializable,
                "created_at": analysis_created_at,
                "updated_at": datetime.utcnow().isoformat(),
            },
            f,
            ensure_ascii=True,
            indent=2,
        )


def _load_analysis_state() -> None:
    if not _ANALYSIS_FILE.exists():
        return
    try:
        from app.schemas import EOBAnalysis
        with open(_ANALYSIS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        created_map = payload.get("created_at", {})
        for aid, data in payload.get("analyses", {}).items():
            try:
                eob_analyses[aid] = EOBAnalysis.model_validate(data)
                # Backfill a creation timestamp for legacy records so they are
                # still subject to retention purging.
                analysis_created_at[aid] = created_map.get(aid, datetime.utcnow().isoformat())
            except Exception:
                pass
    except Exception as e:
        print(f"Warning: Failed to load analysis state: {e}")


def save_analysis(analysis_id: str, analysis) -> None:
    """Store an analysis in memory and persist to disk."""
    eob_analyses[analysis_id] = analysis
    analysis_created_at[analysis_id] = datetime.utcnow().isoformat()
    _save_analysis_state()


def delete_analysis(analysis_id: str) -> bool:
    """Permanently remove a stored analysis and its PHI from memory and disk.

    Payment state (keyed by the irreversible file hash) is intentionally left
    intact so a paying user is never double-charged if they re-upload later.
    Returns True if an analysis was removed, False if nothing was found.
    """
    removed = eob_analyses.pop(analysis_id, None) is not None
    analysis_created_at.pop(analysis_id, None)
    if removed:
        _save_analysis_state()
    return removed


def purge_expired_analyses(retention_hours: int | None = None) -> int:
    """Delete analyses older than the retention window. Returns count purged.

    This bounds how long parsed PHI lives on the server. Payment records are
    not touched, so re-uploading the same file is still recognized as paid.
    """
    hours = retention_hours if retention_hours is not None else ANALYSIS_RETENTION_HOURS
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    expired: list[str] = []
    for aid, created_iso in list(analysis_created_at.items()):
        try:
            created = datetime.fromisoformat(created_iso)
        except (TypeError, ValueError):
            # Unparseable timestamp — treat as expired to err toward privacy.
            expired.append(aid)
            continue
        if created < cutoff:
            expired.append(aid)

    for aid in expired:
        eob_analyses.pop(aid, None)
        analysis_created_at.pop(aid, None)

    if expired:
        _save_analysis_state()
    return len(expired)


_load_payment_state()
_load_outcome_state()
_load_analysis_state()
# Purge any analyses that already exceeded the retention window before this
# process started (e.g. after a restart). Keeps stored PHI within policy.
purge_expired_analyses()