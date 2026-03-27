import json
import os
import smtplib
from datetime import datetime, timedelta, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"
EMAIL_FILE = DATA_DIR / "email_subscribers.jsonl"


def _ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)


def subscribe_email(email: str, analysis_id: str, savings_amount: float = 0.0) -> dict:
    """Store an email subscription. Returns {'is_new': bool}."""
    _ensure_data_dir()

    # Check for duplicate (same email + analysis_id)
    if EMAIL_FILE.exists():
        with open(EMAIL_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("email") == email and rec.get("analysis_id") == analysis_id:
                        return {"is_new": False}
                except Exception:
                    pass

    record = {
        "email": email,
        "analysis_id": analysis_id,
        "savings_amount": savings_amount,
        "subscribed_at": datetime.utcnow().isoformat(),
    }
    with open(EMAIL_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return {"is_new": True}


def get_all_subscribers() -> list:
    """Return all email subscriber records."""
    if not EMAIL_FILE.exists():
        return []

    subscribers = []
    with open(EMAIL_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                subscribers.append(json.loads(line))
            except Exception:
                pass

    return subscribers


def get_signup_counts_by_day(days: int = 7) -> list:
    """Return signup counts per day for the last N days."""
    today = date.today()
    date_range = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    counts = {d: 0 for d in date_range}

    for sub in get_all_subscribers():
        ts = sub.get("subscribed_at", "")[:10]
        if ts in counts:
            counts[ts] += 1

    return [{"date": d, "signups": counts[d]} for d in date_range]


def send_reminder_emails(frontend_url: str) -> dict:
    """
    Send reminder emails to all subscribers via SMTP.
    Requires SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD in environment.
    Returns {"sent": int, "failed": int, ...}.
    """
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    from_email = os.getenv("SMTP_FROM_EMAIL", smtp_username).strip()
    from_name = os.getenv("SMTP_FROM_NAME", "Lower My Medical Bills").strip()

    if not smtp_host or not smtp_username or not smtp_password:
        return {
            "sent": 0,
            "failed": 0,
            "error": (
                "SMTP not configured. Add SMTP_HOST, SMTP_USERNAME, and "
                "SMTP_PASSWORD to your .env file."
            ),
        }

    subscribers = get_all_subscribers()
    sent = 0
    failed = 0
    send_errors = []

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_username, smtp_password)

            for sub in subscribers:
                email = sub.get("email", "").strip()
                analysis_id = sub.get("analysis_id", "")
                savings = sub.get("savings_amount", 0.0) or 0.0

                if not email or not analysis_id:
                    continue

                results_link = f"{frontend_url}/results/{analysis_id}"
                tracker_link = f"{frontend_url}/appeal-tracker/{analysis_id}"
                subject = "Your medical bill savings are still waiting"

                text_body = (
                    f"Hi,\n\n"
                    f"You analyzed a medical bill with ${savings:.2f} in potential savings "
                    f"— but your appeal isn't filed yet.\n\n"
                    f"Your personalized appeal package is still available. "
                    f"Pick up where you left off:\n\n"
                    f"{results_link}\n\n"
                    f"Track appeal progress here:\n"
                    f"{tracker_link}\n\n"
                    f"—The Lower My Medical Bills team\n\n"
                    f"(You received this because you signed up for reminders. "
                    f"Upload a new EOB any time at {frontend_url}.)"
                )

                html_body = f"""<html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;color:#222;line-height:1.6">
<h2 style="color:#0066cc">Your medical bill savings are still waiting</h2>
<p>You analyzed a medical bill with <strong>${savings:.2f} in potential savings</strong>
— but your appeal isn't filed yet.</p>
<p>Your personalized appeal package is still available:</p>
<p style="text-align:center;margin:32px 0">
  <a href="{results_link}"
     style="background:#0066cc;color:#fff;padding:14px 28px;border-radius:6px;
            text-decoration:none;font-weight:bold;display:inline-block">
    View My Appeal Package &rarr;
  </a>
</p>
<p style="text-align:center;margin:16px 0">
    <a href="{tracker_link}" style="color:#0066cc;font-weight:600;text-decoration:none">
        Update my appeal tracker
    </a>
</p>
<p>Unlock your templates to dispute charges and get money back.</p>
<hr style="border:none;border-top:1px solid #eee;margin:32px 0"/>
<p style="color:#999;font-size:12px">
  You received this because you signed up for reminders.
  Upload a new EOB any time at <a href="{frontend_url}">{frontend_url}</a>.
</p>
</body></html>"""

                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = f"{from_name} <{from_email}>"
                msg["To"] = email

                msg.attach(MIMEText(text_body, "plain", "utf-8"))
                msg.attach(MIMEText(html_body, "html", "utf-8"))

                try:
                    server.sendmail(from_email, [email], msg.as_string())
                    sent += 1
                except Exception as exc:
                    failed += 1
                    send_errors.append(f"{email}: {exc}")

    except Exception as exc:
        return {"sent": sent, "failed": failed, "error": str(exc)}

    result = {"sent": sent, "failed": failed}
    if send_errors:
        result["errors"] = send_errors
    return result
