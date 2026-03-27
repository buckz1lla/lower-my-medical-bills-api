from typing import Optional
import os

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.security import is_owner_authenticated
from app.services.appeal_tracker_service import (
    VALID_STATUSES,
    get_tracker,
    tracker_summary,
    upsert_tracker,
)

router = APIRouter()


def _require_owner_or_api_key(request: Request, api_key: Optional[str]) -> None:
    expected = os.getenv("ANALYTICS_API_KEY", "").strip()
    if is_owner_authenticated(request):
        return
    if expected and api_key == expected:
        return
    raise HTTPException(status_code=401, detail="Owner authentication required.")


class AppealTrackerUpdateRequest(BaseModel):
    analysis_id: str
    status: str
    note: Optional[str] = ""
    next_follow_up_date: Optional[str] = None


@router.get("/appeals/tracker/{analysis_id}")
async def get_appeal_tracker(analysis_id: str):
    record = get_tracker(analysis_id)
    if not record:
        return {
            "analysis_id": analysis_id,
            "status": "not_started",
            "note": "",
            "next_follow_up_date": None,
            "updated_at": None,
        }
    return record


@router.post("/appeals/tracker/update")
async def update_appeal_tracker(payload: AppealTrackerUpdateRequest):
    if not payload.analysis_id.strip():
        raise HTTPException(status_code=422, detail="analysis_id is required")

    try:
        updated = upsert_tracker(
            analysis_id=payload.analysis_id.strip(),
            status=payload.status,
            note=payload.note,
            next_follow_up_date=payload.next_follow_up_date,
        )
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Allowed values: {', '.join(sorted(VALID_STATUSES))}",
        )

    return {"ok": True, "tracker": updated}


@router.get("/analytics/appeal-retention")
async def get_appeal_retention_analytics(
    request: Request,
    days: int = Query(30, ge=1, le=120),
    api_key: Optional[str] = Query(None),
):
    _require_owner_or_api_key(request, api_key)

    return tracker_summary(days=days)
