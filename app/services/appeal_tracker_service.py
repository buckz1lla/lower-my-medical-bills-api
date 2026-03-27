import json
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent.parent / "data"
TRACKER_FILE = DATA_DIR / "appeal_tracker.jsonl"

VALID_STATUSES = {
    "not_started",
    "drafting",
    "filed",
    "insurer_review",
    "needs_documents",
    "approved",
    "denied",
}


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(exist_ok=True)


def _read_all() -> list[dict]:
    if not TRACKER_FILE.exists():
        return []

    rows: list[dict] = []
    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def _write_all(rows: list[dict]) -> None:
    _ensure_data_dir()
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def get_tracker(analysis_id: str) -> Optional[dict]:
    for row in reversed(_read_all()):
        if row.get("analysis_id") == analysis_id:
            return row
    return None


def upsert_tracker(
    analysis_id: str,
    status: str,
    note: Optional[str],
    next_follow_up_date: Optional[str],
) -> dict:
    normalized = (status or "").strip().lower()
    if normalized not in VALID_STATUSES:
        raise ValueError("Invalid status")

    rows = _read_all()
    now = datetime.utcnow().isoformat()
    existing_index = None
    for idx, row in enumerate(rows):
        if row.get("analysis_id") == analysis_id:
            existing_index = idx
            break

    prior = rows[existing_index] if existing_index is not None else {}
    if next_follow_up_date:
        follow_up = next_follow_up_date
    else:
        follow_up = prior.get("next_follow_up_date") or (date.today() + timedelta(days=30)).isoformat()

    updated = {
        "analysis_id": analysis_id,
        "status": normalized,
        "note": (note or "").strip(),
        "next_follow_up_date": follow_up,
        "updated_at": now,
        "created_at": prior.get("created_at") or now,
    }

    if existing_index is None:
        rows.append(updated)
    else:
        rows[existing_index] = updated

    _write_all(rows)
    return updated


def tracker_summary(days: int = 30) -> dict:
    rows = _read_all()
    status_counts = {s: 0 for s in sorted(VALID_STATUSES)}
    recent_updates = 0
    today = date.today()

    for row in rows:
        status = (row.get("status") or "").strip().lower()
        if status in status_counts:
            status_counts[status] += 1

        updated_at = str(row.get("updated_at") or "")
        day_str = updated_at[:10]
        if not day_str:
            continue
        try:
            updated_day = datetime.strptime(day_str, "%Y-%m-%d").date()
            if (today - updated_day).days <= days:
                recent_updates += 1
        except Exception:
            pass

    follow_up_due = 0
    for row in rows:
        due = str(row.get("next_follow_up_date") or "")
        if not due:
            continue
        try:
            due_day = datetime.strptime(due, "%Y-%m-%d").date()
            if due_day <= today and row.get("status") not in {"approved", "denied"}:
                follow_up_due += 1
        except Exception:
            pass

    return {
        "days": days,
        "total_trackers": len(rows),
        "recent_updates": recent_updates,
        "follow_up_due": follow_up_due,
        "statuses": status_counts,
        "rows": rows[-50:],
    }
