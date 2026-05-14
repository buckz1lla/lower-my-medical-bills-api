import json
import re
from pathlib import Path
from typing import Optional

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "cms_rates.json"

# Load once at import time
with open(_DATA_PATH, "r", encoding="utf-8") as f:
    _CMS_RATES: list[dict] = json.load(f)

_BY_CPT: dict[str, dict] = {row["cpt"]: row for row in _CMS_RATES}

# --- Verdict thresholds (billed / medicare_rate) ---
# Commercial payers typically reimburse 1.2–2.0x Medicare.
# Providers bill at chargemaster rates which are often 2–5x+.
_THRESHOLDS = [
    (1.5,  "typical",   "Within the typical range for commercially billed procedures."),
    (2.5,  "moderate",  "Somewhat above the Medicare benchmark — may still fall within commercial insurer norms."),
    (4.0,  "high",      "Well above the Medicare rate. Worth verifying with your insurer and asking for an itemized bill."),
    (float("inf"), "very_high", "Significantly above the Medicare rate — a strong candidate for negotiation, appeal, or billing error review."),
]


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def search_procedures(query: str, limit: int = 8) -> list[dict]:
    """Return up to `limit` procedures whose description best matches the query."""
    tokens = _tokenize(query)
    if not tokens:
        return []

    scored = []
    for row in _CMS_RATES:
        desc_tokens = _tokenize(row["description"])
        cat_tokens = _tokenize(row["category"])
        overlap = len(tokens & (desc_tokens | cat_tokens))
        if overlap:
            scored.append((overlap, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [row for _, row in scored[:limit]]


def check_fair_price(
    billed_amount: float,
    cpt_code: Optional[str] = None,
    procedure_query: Optional[str] = None,
) -> dict:
    """
    Compare a billed amount against the CMS Medicare benchmark.

    Provide either `cpt_code` (exact lookup) or `procedure_query` (best-match).
    Returns a verdict dict, or raises ValueError if no procedure can be found.
    """
    if billed_amount <= 0:
        raise ValueError("billed_amount must be greater than zero.")

    # Resolve procedure
    if cpt_code:
        normalized = cpt_code.strip().lstrip("0") if False else cpt_code.strip()
        procedure = _BY_CPT.get(normalized)
        if procedure is None:
            raise ValueError(f"CPT code '{cpt_code}' not found in our benchmark data. Try searching by procedure name instead.")
    elif procedure_query:
        results = search_procedures(procedure_query, limit=1)
        if not results:
            raise ValueError("No matching procedure found. Try a different description or enter a CPT code.")
        procedure = results[0]
    else:
        raise ValueError("Provide either cpt_code or procedure_query.")

    medicare_rate = procedure["medicare_rate"]
    ratio = round(billed_amount / medicare_rate, 2)

    # Determine verdict
    verdict_key = "very_high"
    verdict_note = ""
    for threshold, key, note in _THRESHOLDS:
        if ratio <= threshold:
            verdict_key = key
            verdict_note = note
            break

    # Typical commercial range: 1.2–2.0x Medicare
    typical_low = round(medicare_rate * 1.2, 2)
    typical_high = round(medicare_rate * 2.0, 2)

    return {
        "cpt_code": procedure["cpt"],
        "procedure_name": procedure["description"],
        "category": procedure["category"],
        "medicare_rate": medicare_rate,
        "billed_amount": round(billed_amount, 2),
        "ratio": ratio,
        "verdict": verdict_key,
        "verdict_note": verdict_note,
        "typical_commercial_low": typical_low,
        "typical_commercial_high": typical_high,
        "disclaimer": (
            "Medicare rates are a public benchmark published by CMS. "
            "Actual allowed amounts vary by insurer, plan type, and geographic region. "
            "This tool does not constitute legal or financial advice."
        ),
    }
