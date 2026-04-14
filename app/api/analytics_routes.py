from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from supabase import create_client
from app.security import is_owner_authenticated

router = APIRouter()

TRACKED_EVENTS = [
    "results_page_viewed",
    "checkout_started",
    "payment_completed",
    "pdf_downloaded",
    "affiliate_link_clicked",
    "email_subscribed",
    "appeal_tracker_viewed",
    "appeal_tracker_updated",
]


def _analytics_dir() -> Path:
    analytics_dir = Path(__file__).parent.parent.parent / "analytics"
    analytics_dir.mkdir(exist_ok=True)
    return analytics_dir


def _append_jsonl(log_file: Path, payload: dict) -> None:
    with open(log_file, "a") as f:
        f.write(json.dumps(payload) + "\n")

# Simple in-memory analytics (can upgrade to database later)
class AnalyticsEvent(BaseModel):
    event: str
    data: Optional[Dict[str, Any]] = {}
    timestamp: Optional[str] = None
    userAgent: Optional[str] = None


# Initialize Supabase client.
# Prefer the service-role key on the backend because the events table does not
# grant anon insert access under the current RLS policy.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.getenv("SUPABASE_ANON_KEY", "").strip()
supabase_client = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Warning: Failed to initialize Supabase: {e}")


# Log events to Supabase (primary) then file (fallback)
def log_event_to_database(event: AnalyticsEvent):
    """Store analytics events in Supabase with fallback to file"""
    event_dict = {
        "event_name": event.event,
        "event_data": event.data or {},
        "timestamp": event.timestamp or datetime.now().isoformat(),
        "analysis_id": event.data.get("analysisId") if event.data else None,
        "session_id": event.data.get("sessionId") if event.data else None,
    }
    
    # Try Supabase first
    if supabase_client:
        try:
            supabase_client.table("events").insert(event_dict).execute()
            return True
        except Exception as e:
            log_storage_fallback_alert(event, f"supabase_insert_error: {e}")
            print(f"Supabase insert error: {e}, falling back to file logging")
    else:
        log_storage_fallback_alert(event, "supabase_client_not_initialized")
    
    # Fallback to file logging
    log_event_to_file(event)
    return False


def log_event_to_file(event: AnalyticsEvent):
    """Log analytics events to a file for later analysis"""
    analytics_dir = _analytics_dir()
    
    # Create a daily log file
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = analytics_dir / f"analytics-{today}.jsonl"
    
    # Append event to log (JSONL format for easy parsing)
    event_dict = {
        "event": event.event,
        "data": event.data,
        "timestamp": event.timestamp or datetime.now().isoformat(),
        "userAgent": event.userAgent
    }
    
    try:
        _append_jsonl(log_file, event_dict)
    except Exception as e:
        print(f"Error logging analytics: {e}")


def log_storage_fallback_alert(event: AnalyticsEvent, reason: str):
    """Write high-signal fallback alerts so storage regressions are visible."""
    analytics_dir = _analytics_dir()
    today = datetime.now().strftime("%Y-%m-%d")
    alert_file = analytics_dir / f"alerts-{today}.jsonl"
    payload = {
        "type": "analytics_storage_fallback",
        "timestamp": datetime.now().isoformat(),
        "reason": reason,
        "event": event.event,
        "analysisId": event.data.get("analysisId") if event.data else None,
        "sessionId": event.data.get("sessionId") if event.data else None,
    }
    try:
        _append_jsonl(alert_file, payload)
    except Exception as e:
        print(f"Error logging fallback alert: {e}")


def _empty_event_counts() -> Dict[str, int]:
    return {name: 0 for name in TRACKED_EVENTS}


def _read_day_event_counts(day_str: str) -> Dict[str, int]:
    analytics_dir = _analytics_dir()
    log_file = analytics_dir / f"analytics-{day_str}.jsonl"
    counts = _empty_event_counts()

    if not log_file.exists():
        return counts

    try:
        with open(log_file, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                event_dict = json.loads(line)
                event_name = event_dict.get("event", "")
                if event_name in counts:
                    counts[event_name] += 1
    except Exception as e:
        print(f"Error reading analytics for {day_str}: {e}")

    return counts


def _read_day_events(day_str: str) -> list[dict]:
    analytics_dir = _analytics_dir()
    log_file = analytics_dir / f"analytics-{day_str}.jsonl"
    events: list[dict] = []

    if not log_file.exists():
        return events

    try:
        with open(log_file, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                events.append(json.loads(line))
    except Exception as e:
        print(f"Error reading events for {day_str}: {e}")

    return events


def _mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{local[0]}*@{domain}" if local else None
    return f"{local[:2]}***@{domain}"


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _enforce_analytics_access(api_key: Optional[str], request: Request) -> None:
    """
    Protect analytics endpoints when ANALYTICS_API_KEY is configured.
    If no env key is set, endpoints remain open for local/dev use.
    """
    expected = os.getenv("ANALYTICS_API_KEY", "").strip()
    if is_owner_authenticated(request):
        return
    if not expected:
        return
    if api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid analytics API key")


@router.post("/analytics/track")
async def track_event(event: AnalyticsEvent):
    """
    Track user events (payments, downloads, affiliate clicks, etc.)
    
    Events include:
    - results_page_viewed: User viewed analysis results
    - payment_completed: User paid for templates
    - pdf_downloaded: User downloaded PDF
    - affiliate_link_clicked: User clicked affiliate link
    """
    try:
        stored_in_database = log_event_to_database(event)
        return {
            "status": "tracked",
            "event": event.event,
            "timestamp": event.timestamp or datetime.now().isoformat(),
            "storage": "supabase" if stored_in_database else "file_fallback",
        }
    except Exception as e:
        print(f"Analytics tracking error: {e}")
        # Don't fail user experience if analytics fails
        return {"status": "tracked", "note": "logged locally"}


@router.get("/analytics/summary")
async def get_analytics_summary(request: Request, api_key: Optional[str] = Query(None)):
    """
    Get a summary of today's analytics
    Note: This is a simple endpoint for debugging. Upgrade to database for production.
    """
    _enforce_analytics_access(api_key, request)
    analytics_dir = _analytics_dir()
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = analytics_dir / f"analytics-{today}.jsonl"
    
    summary = {
        "date": today,
        "total_events": 0,
        "events": {},
        "affiliate_clicks": 0,
        "payments": 0,
        "downloads": 0
    }
    
    if log_file.exists():
        try:
            with open(log_file, "r") as f:
                for line in f:
                    if line.strip():
                        event_dict = json.loads(line)
                        event_name = event_dict.get("event", "unknown")
                        
                        summary["total_events"] += 1
                        summary["events"][event_name] = summary["events"].get(event_name, 0) + 1
                        
                        if "affiliate" in event_name:
                            summary["affiliate_clicks"] += 1
                        if "payment" in event_name:
                            summary["payments"] += 1
                        if "download" in event_name:
                            summary["downloads"] += 1
        except Exception as e:
            print(f"Error reading analytics: {e}")
    
    return summary


@router.get("/analytics/storage-alerts")
async def get_storage_alerts(
    request: Request,
    days: int = Query(7, ge=1, le=30),
    max_items: int = Query(50, ge=1, le=200),
    api_key: Optional[str] = Query(None),
):
    """
    Return recent fallback alerts from file-based alert logs.
    Useful for quickly spotting storage regressions in production.
    """
    _enforce_analytics_access(api_key, request)
    today = datetime.now().date()
    analytics_dir = _analytics_dir()
    rows: list[dict] = []

    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        alert_file = analytics_dir / f"alerts-{day_str}.jsonl"
        if not alert_file.exists():
            continue
        try:
            with open(alert_file, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    rows.append(json.loads(line))
        except Exception as e:
            print(f"Error reading alerts for {day_str}: {e}")

    rows.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return {
        "days": days,
        "count": len(rows),
        "alerts": rows[:max_items],
    }


@router.get("/analytics/funnel")
async def get_analytics_funnel(request: Request, api_key: Optional[str] = Query(None)):
    """
    Get today's funnel metrics and conversion rates.

    Funnel:
    - results_page_viewed -> payment_completed -> pdf_downloaded
    - affiliate_link_clicked tracked as CTR from results views
    """
    _enforce_analytics_access(api_key, request)
    today = datetime.now().strftime("%Y-%m-%d")
    counts = _read_day_event_counts(today)

    views = counts["results_page_viewed"]
    payments = counts["payment_completed"]
    downloads = counts["pdf_downloaded"]
    affiliate_clicks = counts["affiliate_link_clicked"]

    return {
        "date": today,
        "counts": counts,
        "funnel": {
            "views_to_payment_percent": _pct(payments, views),
            "payment_to_download_percent": _pct(downloads, payments),
            "views_to_download_percent": _pct(downloads, views),
            "affiliate_ctr_percent": _pct(affiliate_clicks, views),
        },
    }


@router.get("/analytics/timeseries")
async def get_analytics_timeseries(
    request: Request,
    days: int = Query(7, ge=1, le=90),
    api_key: Optional[str] = Query(None),
):
    """
    Get per-day analytics counts and funnel rates for the last N days.
    """
    _enforce_analytics_access(api_key, request)
    today = datetime.now().date()
    rows = []

    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        counts = _read_day_event_counts(day_str)

        views = counts["results_page_viewed"]
        payments = counts["payment_completed"]
        downloads = counts["pdf_downloaded"]
        affiliate_clicks = counts["affiliate_link_clicked"]

        rows.append({
            "date": day_str,
            "counts": counts,
            "funnel": {
                "views_to_payment_percent": _pct(payments, views),
                "payment_to_download_percent": _pct(downloads, payments),
                "views_to_download_percent": _pct(downloads, views),
                "affiliate_ctr_percent": _pct(affiliate_clicks, views),
            },
        })

    return {
        "days": days,
        "series": rows,
    }


@router.get("/analytics/funnel-7d")
async def get_analytics_funnel_7d(request: Request, api_key: Optional[str] = Query(None)):
    """
    Get aggregate funnel metrics for the last 7 days.
    """
    _enforce_analytics_access(api_key, request)
    today = datetime.now().date()
    aggregate = _empty_event_counts()

    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        counts = _read_day_event_counts(day_str)
        for event_name in aggregate:
            aggregate[event_name] += counts[event_name]

    views = aggregate["results_page_viewed"]
    payments = aggregate["payment_completed"]
    downloads = aggregate["pdf_downloaded"]
    affiliate_clicks = aggregate["affiliate_link_clicked"]

    return {
        "date_range": {
            "start": (today - timedelta(days=6)).strftime("%Y-%m-%d"),
            "end": today.strftime("%Y-%m-%d"),
        },
        "counts": aggregate,
        "funnel": {
            "views_to_payment_percent": _pct(payments, views),
            "payment_to_download_percent": _pct(downloads, payments),
            "views_to_download_percent": _pct(downloads, views),
            "affiliate_ctr_percent": _pct(affiliate_clicks, views),
        },
    }


@router.get("/analytics/revenue")
async def get_revenue_analytics(
    request: Request,
    days: int = Query(7, ge=1, le=90),
    api_key: Optional[str] = Query(None),
):
    """
    Revenue-focused analytics from payment_completed events.

    Returns:
    - total revenue
    - payment count
    - average order value
    - recent payments with masked customer email
    """
    _enforce_analytics_access(api_key, request)
    today = datetime.now().date()
    payment_rows = []
    daily_revenue = []

    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        day_total = 0.0
        for evt in _read_day_events(day_str):
            if evt.get("event") != "payment_completed":
                continue

            data = evt.get("data", {}) or {}
            amount = float(data.get("amount") or 0)
            day_total += amount
            payment_rows.append({
                "timestamp": evt.get("timestamp"),
                "analysis_id": data.get("analysisId"),
                "amount": round(amount, 2),
                "customer_email": data.get("customer_email"),
            })
        daily_revenue.append({
            "date": day_str,
            "revenue": round(day_total, 2),
        })

    payment_rows.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    total_revenue = round(sum(row["amount"] for row in payment_rows), 2)
    payment_count = len(payment_rows)
    average_order_value = round(total_revenue / payment_count, 2) if payment_count else 0.0

    return {
        "days": days,
        "currency": "USD",
        "payment_count": payment_count,
        "total_revenue": total_revenue,
        "average_order_value": average_order_value,
        "daily_revenue": daily_revenue,
        "recent_payments": [
            {
                "timestamp": row["timestamp"],
                "analysis_id": row["analysis_id"],
                "amount": row["amount"],
                "customer_email": _mask_email(row["customer_email"]),
            }
            for row in payment_rows[:15]
        ],
    }


@router.get("/analytics/price-experiment")
async def get_price_experiment_analytics(
    request: Request,
    days: int = Query(30, ge=1, le=90),
    api_key: Optional[str] = Query(None),
):
    """
    Summarize conversion and revenue by price variant for simple A/B testing.
    """
    _enforce_analytics_access(api_key, request)
    today = datetime.now().date()
    variants: dict[str, dict] = {}

    def bucket(variant_name: str) -> dict:
        key = (variant_name or "unknown").strip().lower() or "unknown"
        if key not in variants:
            variants[key] = {
                "variant": key,
                "results_views": 0,
                "checkout_started": 0,
                "payments": 0,
                "revenue": 0.0,
            }
        return variants[key]

    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        for evt in _read_day_events(day_str):
            event_name = evt.get("event")
            data = evt.get("data", {}) or {}
            variant = str(data.get("price_variant") or "unknown")
            row = bucket(variant)

            if event_name == "results_page_viewed":
                row["results_views"] += 1
            elif event_name == "checkout_started":
                row["checkout_started"] += 1
            elif event_name == "payment_completed":
                row["payments"] += 1
                row["revenue"] += float(data.get("amount") or 0)

    rows = sorted(variants.values(), key=lambda r: r["variant"])
    for row in rows:
        row["revenue"] = round(row["revenue"], 2)
        row["views_to_checkout_percent"] = _pct(row["checkout_started"], row["results_views"])
        row["checkout_to_payment_percent"] = _pct(row["payments"], row["checkout_started"])
        row["views_to_payment_percent"] = _pct(row["payments"], row["results_views"])
        row["avg_order_value"] = round(row["revenue"] / row["payments"], 2) if row["payments"] else 0.0

    total_revenue = round(sum(row["revenue"] for row in rows), 2)
    total_payments = sum(row["payments"] for row in rows)
    total_views = sum(row["results_views"] for row in rows)

    return {
        "days": days,
        "totals": {
            "results_views": total_views,
            "payments": total_payments,
            "revenue": total_revenue,
            "views_to_payment_percent": _pct(total_payments, total_views),
        },
        "variants": rows,
    }
