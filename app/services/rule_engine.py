import re
import uuid
from datetime import date, timedelta
from typing import List, Optional

from app import schemas


# ---------------------------------------------------------------------------
# X12 Claim Adjustment Reason Code (CARC) Library
# Source: X12 CARC/RARC code set (CMS published list)
# Each entry drives: explanation surfaced to user, recommended action,
# calibrated appeal success probability, difficulty, time estimate, and severity.
# ---------------------------------------------------------------------------
CARC_CODE_LIBRARY = {
    "CO-4": {
        "explanation": "Procedure code is inconsistent with the modifier billed, or a required modifier is missing.",
        "action": "Contact your provider's billing office. Request they verify the modifier submitted and resubmit a corrected claim. This is almost always a fixable coding error.",
        "success_probability": 0.72,
        "difficulty_level": "easy",
        "time_estimate_days": 14,
        "severity": "medium",
        "category": "billing_error",
    },
    "CO-11": {
        "explanation": "Diagnosis code is inconsistent with the procedure ordered. Insurer does not consider the procedure medically necessary for the billed diagnosis.",
        "action": "Request your provider submit a corrected claim with the accurate diagnosis code, or obtain a letter of medical necessity linking this procedure to your condition. A physician attestation is typically required.",
        "success_probability": 0.61,
        "difficulty_level": "medium",
        "time_estimate_days": 30,
        "severity": "high",
        "category": "appeal",
    },
    "CO-16": {
        "explanation": "Claim/service lacks information needed for adjudication. This is a submission error — often a missing field, date, or authorization number — and is one of the most correctable denial types.",
        "action": "Contact provider billing immediately. Ask what specific information is missing and request a corrected claim resubmission. Track the resubmission and follow up within 10 days.",
        "success_probability": 0.82,
        "difficulty_level": "easy",
        "time_estimate_days": 10,
        "severity": "high",
        "category": "billing_error",
    },
    "CO-18": {
        "explanation": "Exact duplicate claim or service. This claim was identified as a duplicate of a previously submitted or adjudicated claim.",
        "action": "Confirm with your provider billing office that this is not a system-generated duplicate submission. If both services were genuinely separate encounters, ask the provider to resubmit with distinct dates, service descriptions, or line-item details that differentiate them. If it is a true duplicate, no additional payment is owed.",
        "success_probability": 0.60,
        "difficulty_level": "easy",
        "time_estimate_days": 14,
        "severity": "medium",
        "category": "billing_error",
    },
    "CO-22": {
        "explanation": "This care may be covered by another payer per coordination of benefits (COB). Insurer believes you have another insurance policy that should pay first.",
        "action": "If you have only one insurance plan, send your insurer written confirmation. If you have dual coverage, verify the correct primary/secondary payer order with both insurers. File with the correct primary payer first.",
        "success_probability": 0.58,
        "difficulty_level": "medium",
        "time_estimate_days": 21,
        "severity": "medium",
        "category": "billing_error",
    },
    "CO-26": {
        "explanation": "Expenses were incurred prior to your coverage effective date. The service date precedes the date your insurance coverage began.",
        "action": "Verify your coverage effective date with your insurer. If you were covered under a prior plan on the date of service, submit to that prior insurer. If the claim date is incorrect, ask your provider to resubmit a corrected claim with the accurate service date. If a coverage gap exists due to a qualifying life event, check whether retroactive coverage applies.",
        "success_probability": 0.35,
        "difficulty_level": "hard",
        "time_estimate_days": 30,
        "severity": "high",
        "category": "appeal",
    },
    "CO-27": {
        "explanation": "Expenses were incurred after your coverage was terminated. The service date falls after the date your insurance coverage ended.",
        "action": "Verify your coverage termination date with your insurer. Check whether COBRA or continuation coverage was elected — COBRA coverage can be retroactive if elected within 60 days. If the claim date is wrong, request a corrected claim from your provider. If coverage lapsed due to employer error, contact your HR department immediately.",
        "success_probability": 0.30,
        "difficulty_level": "hard",
        "time_estimate_days": 30,
        "severity": "high",
        "category": "appeal",
    },
    "CO-29": {
        "explanation": "Timely filing limit has been exceeded. Claims must typically be filed within 90–365 days of the service date depending on the plan.",
        "action": "Request proof of timely filing from your provider (clearinghouse receipt, certified mail confirmation, or payer acknowledgment). If the late filing was the provider's fault, request they waive the balance as a professional courtesy. External appeal options are very limited for this denial type.",
        "success_probability": 0.12,
        "difficulty_level": "hard",
        "time_estimate_days": 45,
        "severity": "critical",
        "category": "appeal",
    },
    "CO-45": {
        "explanation": "Contractual adjustment — provider's billed charge exceeds the contracted fee schedule amount. This is a normal insurance adjustment, not a billing error. You are NOT responsible for this write-off amount.",
        "action": "No action needed for the CO-45 write-off itself. Verify your EOB shows you owe only your stated patient responsibility (deductible, coinsurance, or copay), not the full billed amount. Contact insurer if you receive a bill for the written-off portion.",
        "success_probability": 0.0,
        "difficulty_level": "easy",
        "time_estimate_days": 0,
        "severity": "low",
        "category": "informational",
    },
    "CO-50": {
        "explanation": "Non-covered service. This procedure is not a covered benefit under your current plan.",
        "action": "Pull your plan's Summary of Benefits and Coverage (SBC) and locate the exclusion that applies. If the exclusion does not clearly apply, file an appeal citing medical necessity and plan ambiguity. Ask your provider if an alternative covered procedure achieves the same clinical outcome.",
        "success_probability": 0.30,
        "difficulty_level": "hard",
        "time_estimate_days": 45,
        "severity": "high",
        "category": "appeal",
    },
    "CO-55": {
        "explanation": "Claim denied due to a pre-existing condition exclusion. Your plan determined this condition existed before your coverage effective date and is subject to an exclusion period.",
        "action": "Important: Pre-existing condition exclusions are prohibited for most ACA-compliant plans (marketplace and employer group plans since 2014). If your plan is ACA-compliant, file an immediate appeal citing ACA Section 2704. If your plan is grandfathered or a short-term limited-duration plan, review the exclusion period in your plan documents and verify it has not yet elapsed. Request the specific exclusion clause in writing.",
        "success_probability": 0.65,
        "difficulty_level": "medium",
        "time_estimate_days": 30,
        "severity": "high",
        "category": "appeal",
    },
    "CO-58": {
        "explanation": "Claim denied because the treatment or procedure was deemed experimental or investigational by your insurer. The insurer considers this service to lack sufficient clinical evidence for the indicated use.",
        "action": "Request the specific clinical policy and coverage determination criteria your insurer applied. Obtain a detailed letter of medical necessity from your physician that includes peer-reviewed clinical literature supporting the treatment for your diagnosis. Many experimental denials are successfully overturned with physician attestation and published evidence. Request an independent external medical review if your internal appeal is denied.",
        "success_probability": 0.45,
        "difficulty_level": "hard",
        "time_estimate_days": 45,
        "severity": "high",
        "category": "appeal",
    },
    "CO-96": {
        "explanation": "Non-covered charges. Insurer has excluded this charge based on your plan's benefit design.",
        "action": "Request the specific plan exclusion language in writing. Check whether the service was coded correctly — sometimes a differently coded but clinically equivalent service is covered. File an appeal if the exclusion is ambiguous or the coding can be corrected.",
        "success_probability": 0.28,
        "difficulty_level": "hard",
        "time_estimate_days": 45,
        "severity": "high",
        "category": "appeal",
    },
    "CO-97": {
        "explanation": "Payment for this service is included in the allowance for another service or procedure. Often indicates a bundling rule was applied.",
        "action": "Request an itemized bill and ask your provider billing office which global service includes this charge. If the procedures are clinically distinct and should not be bundled, request a corrected claim with supporting documentation.",
        "success_probability": 0.55,
        "difficulty_level": "medium",
        "time_estimate_days": 21,
        "severity": "medium",
        "category": "billing_error",
    },
    "CO-109": {
        "explanation": "Claim not covered by this payer or contractor. The claim may have been filed to the wrong insurer, or your coverage was not active on the date of service.",
        "action": "Verify coverage dates and confirm the correct insurance carrier for this service date. If filed to the wrong payer in error, request the provider refile to the correct insurer. Contact your employer HR or insurance broker if coverage dates are disputed.",
        "success_probability": 0.45,
        "difficulty_level": "medium",
        "time_estimate_days": 21,
        "severity": "high",
        "category": "billing_error",
    },
    "CO-119": {
        "explanation": "Maximum benefit for this time period or service type has been exhausted. You have reached your plan's coverage cap for this benefit category.",
        "action": "Review your plan's benefit limits for this service category. Verify your accumulator balance with your insurer — sometimes benefit counts are applied in error. Ask if a different benefit category applies to this service.",
        "success_probability": 0.20,
        "difficulty_level": "hard",
        "time_estimate_days": 30,
        "severity": "high",
        "category": "appeal",
    },
    "CO-167": {
        "explanation": "Diagnosis is inconsistent with the patient's age or sex for the billed procedure. This is typically a coding or demographic data entry error.",
        "action": "Request your provider verify patient demographics (date of birth, sex) on file with the insurer, correct any error, and resubmit. This is almost always a quick administrative fix.",
        "success_probability": 0.75,
        "difficulty_level": "easy",
        "time_estimate_days": 14,
        "severity": "medium",
        "category": "billing_error",
    },
    "PR-1": {
        "explanation": "Deductible amount applied. You owe this amount toward your annual deductible before insurance pays.",
        "action": "Confirm your current deductible accumulator balance with your insurer. If your deductible has already been fully met this plan year, request claim reprocessing. If not yet met, this charge is likely correct.",
        "success_probability": 0.40,
        "difficulty_level": "medium",
        "time_estimate_days": 14,
        "severity": "medium",
        "category": "appeal",
    },
    "PR-2": {
        "explanation": "Coinsurance amount applied. This is your percentage share of the allowed amount after the deductible is met.",
        "action": "Verify the coinsurance percentage in your plan documents matches what was applied. If the wrong cost-sharing tier was used (e.g., specialist vs. PCP), request reprocessing with the correct tier.",
        "success_probability": 0.38,
        "difficulty_level": "medium",
        "time_estimate_days": 14,
        "severity": "medium",
        "category": "appeal",
    },
    "PR-3": {
        "explanation": "Co-payment amount applied. Fixed amount you owe for this service type.",
        "action": "Verify the copay tier matches your plan documents for this exact service type (ER, specialist, PCP, urgent care). ER copays are typically higher and waived if admitted. If the wrong tier was applied, request reprocessing.",
        "success_probability": 0.30,
        "difficulty_level": "easy",
        "time_estimate_days": 10,
        "severity": "low",
        "category": "appeal",
    },
    "OA-23": {
        "explanation": "Payment adjusted due to a payer/plan payment policy not elsewhere classified.",
        "action": "Request the specific payment policy that triggered this adjustment in writing. If the policy was applied incorrectly or does not clearly apply to your service, file a formal grievance citing incorrect policy application.",
        "success_probability": 0.50,
        "difficulty_level": "medium",
        "time_estimate_days": 30,
        "severity": "medium",
        "category": "appeal",
    },
    "OA-109": {
        "explanation": "Claim or service denied. Administrative denial without a more specific reason code.",
        "action": "Request the full denial notice with the specific reason. Do not accept 'denied' without a reason code — you have the right to a detailed explanation. File an appeal citing the lack of specific reason and requesting reconsideration.",
        "success_probability": 0.55,
        "difficulty_level": "medium",
        "time_estimate_days": 30,
        "severity": "high",
        "category": "appeal",
    },
    "PI-15": {
        "explanation": "Payment adjusted because the submitted authorization number is missing, invalid, or does not apply.",
        "action": "Contact your provider to verify the prior authorization number submitted. If authorization was obtained, request a corrected claim with the valid auth number. If authorization was not obtained, ask provider if a retro-authorization request is possible.",
        "success_probability": 0.52,
        "difficulty_level": "medium",
        "time_estimate_days": 21,
        "severity": "high",
        "category": "billing_error",
    },
    "CO-57": {
        "explanation": "A required referral or authorization for this service was not obtained before the service was provided. Common for specialist visits under HMO and POS plans that require a primary care referral.",
        "action": "Verify whether your plan requires a PCP referral for this specialist or service type. If a referral was issued but not submitted with the claim, ask your PCP and the specialist's billing office to coordinate. If urgency prevented a referral, file an appeal documenting the medical necessity and requesting retroactive authorization.",
        "success_probability": 0.42,
        "difficulty_level": "medium",
        "time_estimate_days": 21,
        "severity": "high",
        "category": "appeal",
    },
    "CO-151": {
        "explanation": "Payment adjusted because the insurer determined the submitted documentation does not support this level of service, length of stay, or care setting. This is a medical necessity or level-of-care denial.",
        "action": "Request your provider submit a detailed letter of medical necessity from the attending physician that documents clinical findings, diagnosis severity, and the rationale for the billed service level. Ask the provider to include specific ICD-10 severity indicators and relevant clinical guidelines. File a formal appeal if the denial is upheld.",
        "success_probability": 0.52,
        "difficulty_level": "hard",
        "time_estimate_days": 45,
        "severity": "high",
        "category": "appeal",
    },
    "CO-170": {
        "explanation": "Payment denied because this service is not covered when performed or billed by this provider type or specialty. Often occurs when a service requires a specific credential, license type, or NPI taxonomy that the billing provider does not hold.",
        "action": "Ask your provider to verify their credentialing and NPI taxonomy code on file with your insurer. If the service was performed by a qualified provider but billed under the wrong NPI, request a corrected claim. If the provider is not credentialed for this service, ask your insurer whether a covered specialist can provide the same service at no additional cost.",
        "success_probability": 0.40,
        "difficulty_level": "medium",
        "time_estimate_days": 21,
        "severity": "high",
        "category": "billing_error",
    },
    "CO-197": {
        "explanation": "Payment denied because prior authorization or precertification was not obtained as required by your plan before the service was performed. This is one of the most common denial types for elective procedures, specialist visits, imaging, and certain diagnostic tests.",
        "action": "Contact your provider's office and ask whether they submitted a prior authorization request and, if so, what authorization number was used. Request a corrected claim resubmission with the valid auth number if one exists. If no authorization was obtained, ask your provider to request retroactive authorization citing medical urgency or provider error. File a formal appeal if retroactive auth is denied.",
        "success_probability": 0.48,
        "difficulty_level": "medium",
        "time_estimate_days": 30,
        "severity": "high",
        "category": "appeal",
    },
    "CO-252": {
        "explanation": "Your insurer requires additional documentation — such as medical records, operative notes, a referral letter, or proof of medical necessity — before this claim can be adjudicated.",
        "action": "Contact your provider immediately and ask them to submit the required documentation to the insurer. Request the insurer specify in writing exactly what documents are needed and confirm receipt once submitted. Most documentation requests are resolved quickly when the provider responds promptly.",
        "success_probability": 0.74,
        "difficulty_level": "easy",
        "time_estimate_days": 14,
        "severity": "medium",
        "category": "billing_error",
    },
}

# Emergency service keywords for No Surprises Act detection
_NSA_EMERGENCY_KEYWORDS = [
    "emergency", "emergent", "er visit", "emergency room", "emergency dept",
    "emergency department", "urgent care", "stabilization", "ambulance",
    "ems", "trauma", "critical care", "emergency services",
]

# ---------------------------------------------------------------------------
# CCI Edit Pairs (Correct Coding Initiative)
# Source: CMS National Correct Coding Initiative Policy Manual
# When both CPT codes in a pair appear on the same claim the component code
# is already bundled into the comprehensive code — billing both is unbundling.
# Each entry: (comprehensive_code, component_code, reason)
# ---------------------------------------------------------------------------
CCI_EDIT_PAIRS = [
    ("93000", "93005", "Complete ECG (93000) already includes the ECG tracing component (93005). The tracing cannot be billed separately."),
    ("93000", "93010", "Complete ECG (93000) already includes the interpretation component (93010). The interpretation cannot be billed separately."),
    ("85025", "85027", "CBC with differential (85025) already includes CBC without differential (85027) — only one can be billed."),
    ("81003", "81001", "Automated urinalysis (81003) already includes non-automated urinalysis (81001) — only one can be billed."),
    ("36415", "36000", "Routine venipuncture (36415) cannot be billed with IV catheter placement (36000) for the same access site."),
    ("71046", "71045", "Two-view chest X-ray (71046) already includes the single-view chest X-ray (71045)."),
    ("45380", "45378", "Colonoscopy with biopsy (45380) already includes diagnostic colonoscopy (45378)."),
    ("43239", "43235", "Upper GI endoscopy with biopsy (43239) already includes diagnostic upper GI endoscopy (43235)."),
    ("27447", "27310", "Total knee arthroplasty (27447) already includes knee manipulation (27310) when performed in the same operative session."),
    ("27447", "27331", "Total knee arthroplasty (27447) already includes knee arthroscopy (27331) when performed in the same operative session."),
    ("27130", "27125", "Total hip arthroplasty (27130) already includes partial hip arthroplasty (27125) — only one can be billed per session."),
    ("99213", "99000", "Office E/M visit (99213) already includes specimen handling — billing 99000 separately is a common unbundling error."),
    ("99214", "99000", "Office E/M visit (99214) already includes specimen handling — billing 99000 separately is a common unbundling error."),
    ("99215", "99000", "Office E/M visit (99215) already includes specimen handling — billing 99000 separately is a common unbundling error."),
    # Cardiology — Echocardiography
    ("93306", "93307", "Complete TTE with Doppler (93306) already includes echocardiography without Doppler (93307). Billing both is an unbundling error."),
    ("93306", "93320", "Complete TTE with Doppler (93306) already includes spectral Doppler echocardiography (93320). Billing both is an unbundling error."),
    ("93306", "93325", "Complete TTE with Doppler (93306) already includes color-flow Doppler (93325). Billing both is an unbundling error."),
    # Cardiology — Cardiovascular Stress Testing
    ("93015", "93016", "Complete cardiovascular stress test (93015) already includes physician supervision (93016). The complete code cannot be unbundled."),
    ("93015", "93017", "Complete cardiovascular stress test (93015) already includes the exercise ECG tracing (93017). The complete code cannot be unbundled."),
    ("93015", "93018", "Complete cardiovascular stress test (93015) already includes physician interpretation and report (93018). The complete code cannot be unbundled."),
    # Radiology — MRI with and without contrast
    ("70553", "70551", "MRI brain with and without contrast (70553) already includes MRI brain without contrast (70551). Billing both is an unbundling error."),
    ("70553", "70552", "MRI brain with and without contrast (70553) already includes MRI brain with contrast (70552). Billing both is an unbundling error."),
    ("72158", "72148", "MRI lumbar spine with and without contrast (72158) already includes MRI lumbar spine without contrast (72148). Billing both is an unbundling error."),
    ("72158", "72149", "MRI lumbar spine with and without contrast (72158) already includes MRI lumbar spine with contrast (72149). Billing both is an unbundling error."),
    ("73723", "73721", "MRI any joint lower extremity with and without contrast (73723) already includes the without-contrast component (73721). Billing both is an unbundling error."),
    ("73223", "73221", "MRI any joint upper extremity with and without contrast (73223) already includes the without-contrast component (73221). Billing both is an unbundling error."),
    # Radiology — CT abdomen/pelvis
    ("74178", "74176", "CT abdomen and pelvis with and without contrast (74178) already includes CT without contrast (74176). Billing both is an unbundling error."),
    ("74178", "74177", "CT abdomen and pelvis with and without contrast (74178) already includes CT with contrast (74177). Billing both is an unbundling error."),
    # Gastroenterology — Colonoscopy
    ("45384", "45378", "Colonoscopy with removal of polyp by hot biopsy forceps (45384) already includes diagnostic colonoscopy (45378). The therapeutic code cannot be unbundled."),
    ("45385", "45378", "Colonoscopy with snare polypectomy (45385) already includes diagnostic colonoscopy (45378). The therapeutic code cannot be unbundled."),
    ("45381", "45378", "Colonoscopy with directed submucosal injection (45381) already includes diagnostic colonoscopy (45378). The therapeutic code cannot be unbundled."),
    # Gastroenterology — Upper GI Endoscopy
    ("43245", "43235", "Upper GI endoscopy with dilation of esophagus (43245) already includes diagnostic upper GI endoscopy (43235). The therapeutic code cannot be unbundled."),
    ("43247", "43235", "Upper GI endoscopy with removal of foreign body (43247) already includes diagnostic upper GI endoscopy (43235). The therapeutic code cannot be unbundled."),
    # Orthopedics — Knee Arthroscopy
    ("29880", "29870", "Knee arthroscopy with medial and lateral meniscectomy (29880) already includes diagnostic knee arthroscopy (29870). Billing the diagnostic code separately is an unbundling error."),
    ("29881", "29870", "Knee arthroscopy with meniscectomy (29881) already includes diagnostic knee arthroscopy (29870). Billing the diagnostic code separately is an unbundling error."),
    ("29882", "29870", "Knee arthroscopy with meniscus repair (29882) already includes diagnostic knee arthroscopy (29870). Billing the diagnostic code separately is an unbundling error."),
    # Orthopedics — Shoulder Arthroscopy
    ("29826", "29819", "Shoulder arthroscopy with decompression (29826) already includes diagnostic shoulder arthroscopy (29819). Billing the diagnostic code separately is an unbundling error."),
    ("29827", "29819", "Shoulder arthroscopy with rotator cuff repair (29827) already includes diagnostic shoulder arthroscopy (29819). Billing the diagnostic code separately is an unbundling error."),
    # Laboratory — Metabolic Panels
    ("80053", "80048", "Comprehensive metabolic panel (80053) already includes all tests in the basic metabolic panel (80048). Billing both on the same date is unbundling."),
    ("80053", "82947", "Comprehensive metabolic panel (80053) already includes glucose (82947). Billing both on the same date is unbundling."),
    ("80053", "84132", "Comprehensive metabolic panel (80053) already includes potassium (84132). Billing both on the same date is unbundling."),
    ("80048", "82947", "Basic metabolic panel (80048) already includes glucose (82947). Billing both on the same date is unbundling."),
    # Laboratory — Lipid Panel
    ("80061", "82465", "Lipid panel (80061) already includes total cholesterol (82465). Billing both on the same date is unbundling."),
    ("80061", "83718", "Lipid panel (80061) already includes HDL cholesterol (83718). Billing both on the same date is unbundling."),
    ("80061", "84478", "Lipid panel (80061) already includes triglycerides (84478). Billing both on the same date is unbundling."),
    # Pathology — Surgical Pathology
    ("88307", "88305", "Surgical pathology Level VI (88307) already includes the Level V examination (88305) for the same specimen. Billing both is unbundling."),
    ("88305", "88300", "Surgical pathology Level V (88305) already includes the Level I gross-only examination (88300) for the same specimen. Billing both is unbundling."),
    # Psychotherapy
    ("90837", "90832", "60-minute individual psychotherapy (90837) already includes the 30-minute service (90832). Billing both on the same date is an unbundling error."),
    ("90837", "90834", "60-minute individual psychotherapy (90837) already includes the 45-minute service (90834). Billing both on the same date is an unbundling error."),
]

# Modifiers that legitimately allow separate billing of CCI component codes.
# When any of these are present on the component code, the provider is asserting
# a distinct, separately-identifiable service.
_BYPASS_MODIFIERS = {"59", "XU", "XE", "XP", "XS"}

# CPT range for E/M services.  Modifier -25 on an E/M code same-day as a
# procedure is a common overbilling pattern.
_EM_CPT_MIN = 99202
_EM_CPT_MAX = 99499


def _has_bypass_modifier(modifier: Optional[str]) -> bool:
    """Return True if the modifier string contains any CCI bypass modifier."""
    if not modifier:
        return False
    parts = re.split(r"[-,\s]+", modifier.strip().lstrip("-").upper())
    return bool(_BYPASS_MODIFIERS.intersection(p for p in parts if p))


def _parse_modifiers(modifier: Optional[str]) -> set:
    """Return a set of individual modifier codes from a modifier string."""
    if not modifier:
        return set()
    parts = re.split(r"[-,\s]+", modifier.strip().lstrip("-").upper())
    return {p for p in parts if p}


def _is_em_cpt(cpt_code: Optional[str]) -> bool:
    """Return True if the CPT code falls in the E/M range (99202–99499)."""
    if not cpt_code:
        return False
    try:
        code_int = int(cpt_code.strip())
        return _EM_CPT_MIN <= code_int <= _EM_CPT_MAX
    except ValueError:
        return False


def _normalize_carc_code(raw_code: str) -> str:
    """Normalize a raw reason code string to a CARC library key (e.g. '45' -> 'CO-45')."""
    if not raw_code:
        return ""
    code = raw_code.strip().upper()
    # Already well-formed: CO-45, PR-1, OA-23, PI-15
    if re.match(r"^(CO|PR|OA|PI|CR)-\d+$", code):
        return code
    # Numeric only — assume CO prefix (most common)
    if re.match(r"^\d+$", code):
        return f"CO-{code}"
    # Concatenated: CO45, PR1, OA23
    match = re.match(r"^(CO|PR|OA|PI|CR)(\d+)$", code)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return code


def _get_carc_data(reason_code: Optional[str]) -> Optional[dict]:
    """Return CARC library entry for a reason code, or None if not found."""
    if not reason_code:
        return None
    return CARC_CODE_LIBRARY.get(_normalize_carc_code(reason_code))


def _fmt_usd(amount: float) -> str:
    return f"${amount:,.2f}"


def _confidence_level(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def _appeal_deadline_fields(visit_date: Optional[date]) -> dict:
    """
    Calculate the standard 180-day appeal deadline from the visit date and
    return a dict suitable for spreading into SavingsOpportunity kwargs.
    Returns empty dict when visit_date is unavailable.
    """
    if not visit_date:
        return {}
    deadline = visit_date + timedelta(days=180)
    today = date.today()
    days_left = (deadline - today).days
    if days_left < 0:
        note = f"Appeal window closed {abs(days_left)} day(s) ago — external review may still be available."
    elif days_left <= 14:
        note = f"URGENT: Appeal deadline is {deadline.strftime('%B %d, %Y')} — only {days_left} day(s) remaining."
    elif days_left <= 45:
        note = f"Act soon: Appeal deadline is {deadline.strftime('%B %d, %Y')} ({days_left} days remaining)."
    else:
        note = f"Appeal deadline: {deadline.strftime('%B %d, %Y')} ({days_left} days remaining)."
    return {"appeal_deadline": deadline, "appeal_deadline_note": note}


def _apply_data_confidence_guard(raw_score: float, missing_data_points: List[str]) -> float:
    # When key plan-state fields are missing, downgrade certainty to avoid overconfident guidance.
    score = raw_score
    if len(missing_data_points) >= 3 and score > 0.69:
        score = 0.69
    if len(missing_data_points) >= 4 and score > 0.55:
        score = 0.55
    return round(score, 2)


def evaluate_claims(
    claims: List[schemas.ClaimGroup],
    user_profile: Optional[schemas.UserProfile] = None,
) -> List[schemas.SavingsOpportunity]:
    """Run all active rules and return savings opportunities."""
    opportunities: List[schemas.SavingsOpportunity] = []

    opportunities.extend(_rule_reason_code_analysis(claims))
    opportunities.extend(_rule_duplicate_charge(claims))
    opportunities.extend(_rule_out_of_network(claims))
    opportunities.extend(_rule_oon_referred_ancillary(claims))
    opportunities.extend(_rule_no_surprises_act(claims))
    opportunities.extend(_rule_upcoding_signal(claims))
    opportunities.extend(_rule_denied_claim_appeal(claims))
    opportunities.extend(_rule_deductible_accumulator(claims, user_profile))
    opportunities.extend(_rule_unbundling(claims))
    opportunities.extend(_rule_modifier_abuse(claims))
    opportunities.extend(_rule_coordination_of_benefits(claims))
    opportunities.extend(_rule_systemic_prior_auth(claims))

    return opportunities


def _rule_deductible_accumulator(
    claims: List[schemas.ClaimGroup],
    user_profile: Optional[schemas.UserProfile],
) -> List[schemas.SavingsOpportunity]:
    """
    When the user provides deductible or out-of-pocket accumulator data,
    check whether cost-sharing charges (PR-1 deductible, PR-2 coinsurance,
    PR-3 copay) were applied after the accumulator was already fully met.
    Insurer accumulator tracking errors are common and correctable with
    a single call to member services plus prior-EOB documentation.
    """
    opportunities: List[schemas.SavingsOpportunity] = []
    if not user_profile:
        return opportunities

    deductible_full = (
        user_profile.annual_deductible is not None
        and user_profile.deductible_met is not None
        and user_profile.annual_deductible > 0
        and user_profile.deductible_met >= user_profile.annual_deductible
    )
    oop_full = (
        user_profile.out_of_pocket_max is not None
        and user_profile.out_of_pocket_spent is not None
        and user_profile.out_of_pocket_max > 0
        and user_profile.out_of_pocket_spent >= user_profile.out_of_pocket_max
    )

    if not deductible_full and not oop_full:
        return opportunities

    for claim in claims:
        for item in claim.line_items:
            if item.patient_responsibility <= 0:
                continue

            code = _normalize_carc_code(item.reason_code or "")
            is_deductible_charge = code == "PR-1" and deductible_full
            is_oop_charge = code in ("PR-2", "PR-3") and oop_full

            if not is_deductible_charge and not is_oop_charge:
                continue

            if is_deductible_charge:
                description = (
                    f"Your annual deductible of {_fmt_usd(user_profile.annual_deductible)} "
                    f"is shown as fully met ({_fmt_usd(user_profile.deductible_met)}), yet a deductible "
                    f"charge of {_fmt_usd(item.patient_responsibility)} was applied to: {item.service_description}."
                )
                action = (
                    "Call your insurer and ask them to verify your deductible accumulator balance on the exact "
                    "date of this service. If the deductible was already met, request claim reprocessing. "
                    "Have your prior EOBs showing the deductible being fully applied ready before you call."
                )
                success_prob = 0.78
                evidence_line = (
                    f"User-reported deductible met: {_fmt_usd(user_profile.deductible_met)} "
                    f"/ {_fmt_usd(user_profile.annual_deductible)}"
                )
            else:
                description = (
                    f"Your out-of-pocket maximum of {_fmt_usd(user_profile.out_of_pocket_max)} "
                    f"appears to have been reached ({_fmt_usd(user_profile.out_of_pocket_spent)} spent), yet "
                    f"cost-sharing of {_fmt_usd(item.patient_responsibility)} was applied to: {item.service_description}."
                )
                action = (
                    "Once your out-of-pocket maximum is met, your insurer must cover 100% of covered in-network "
                    "services for the remainder of the plan year. Call your insurer, request accumulator "
                    "verification, and ask for claim reprocessing if your OOP was already exhausted on this date."
                )
                success_prob = 0.80
                evidence_line = (
                    f"User-reported OOP spent: {_fmt_usd(user_profile.out_of_pocket_spent)} "
                    f"/ {_fmt_usd(user_profile.out_of_pocket_max)}"
                )

            missing_data_points = [
                "Confirmation all prior claims were fully processed before this service date",
                "Complete EOB history showing cumulative deductible/OOP credits for this plan year",
            ]
            score = _apply_data_confidence_guard(success_prob, missing_data_points)

            opportunities.append(
                schemas.SavingsOpportunity(
                    opportunity_id=str(uuid.uuid4()),
                    type="billing_error",
                    claim_id=claim.claim_id,
                    severity="critical",
                    estimated_savings=round(item.patient_responsibility, 2),
                    description=description,
                    recommended_action=action,
                    difficulty_level="easy",
                    time_estimate_days=14,
                    confidence_score=score,
                    confidence_level=_confidence_level(score),
                    flag_reason=(
                        "Patient cost-sharing applied after accumulator appears fully met per user-provided plan data."
                    ),
                    verification_steps=[
                        "Pull all EOBs from this plan year showing deductible and OOP credits applied.",
                        "Log into your insurer's member portal and check the accumulator balance for this plan year.",
                        "Call member services and ask for the accumulator balance as of the exact date of this service.",
                        "Request formal claim reprocessing if the accumulator was already at or above the plan limit.",
                        "File a formal grievance with your EOB history if the insurer disputes the accumulator balance.",
                    ],
                    could_be_correct_if=[
                        "The plan year reset between the accumulator reaching the limit and this service date.",
                        "This service applies to a separate family-tier deductible with a higher limit.",
                        "Some costs may have been credited to a different benefit bucket (dental, vision, out-of-network).",
                    ],
                    evidence=[
                        evidence_line,
                        f"Cost-sharing charge of {_fmt_usd(item.patient_responsibility)} on reason code {code}",
                    ],
                    missing_data_points=missing_data_points,
                    **_appeal_deadline_fields(claim.visit_date),
                )
            )

    return opportunities


def _rule_reason_code_analysis(claims: List[schemas.ClaimGroup]) -> List[schemas.SavingsOpportunity]:
    """
    Map X12 CARC/RARC denial reason codes on denied or partial line items to
    specific, calibrated guidance. This is the core IP of the rule engine —
    every reason code produces a tailored explanation and action rather than
    a generic 'claim denied' message.
    """
    opportunities: List[schemas.SavingsOpportunity] = []

    for claim in claims:
        for item in claim.line_items:
            if item.status not in ("denied", "partial"):
                continue
            carc_data = _get_carc_data(item.reason_code)
            if not carc_data:
                continue
            # CO-45 contractual adjustments are informational — not actionable savings
            if carc_data["category"] == "informational":
                continue

            normalized_code = _normalize_carc_code(item.reason_code)
            estimated_savings = (
                item.patient_responsibility
                if item.patient_responsibility > 0
                else round(item.billed_amount * 0.6, 2)
            )
            missing_data_points = list(claim.missing_data_points or [])
            score = _apply_data_confidence_guard(carc_data["success_probability"], missing_data_points)

            opportunities.append(
                schemas.SavingsOpportunity(
                    opportunity_id=str(uuid.uuid4()),
                    type=carc_data["category"],
                    claim_id=claim.claim_id,
                    severity=carc_data["severity"],
                    estimated_savings=round(estimated_savings, 2),
                    description=f"Denial code {normalized_code}: {carc_data['explanation']}",
                    recommended_action=carc_data["action"],
                    difficulty_level=carc_data["difficulty_level"],
                    time_estimate_days=carc_data["time_estimate_days"],
                    confidence_score=score,
                    confidence_level=_confidence_level(score),
                    flag_reason=f"Reason code {normalized_code} found on a {item.status} line item for: {item.service_description}",
                    verification_steps=[
                        f"Pull the full denial notice for claim {claim.claim_id} from your insurer's member portal.",
                        "Confirm the reason code on your paper EOB matches this code exactly.",
                        "Request an itemized bill from the provider if not already in hand.",
                        "Note the appeal deadline on your EOB — most plans allow 180 days from denial date.",
                    ],
                    could_be_correct_if=[
                        "The code was applied per your plan's standard benefit design for this service type.",
                        "You have already received a prior written determination that this denial is final.",
                    ],
                    evidence=[
                        f"Reason code {normalized_code} on {item.status} line item",
                        f"Service: {item.service_description} — Patient responsibility: {_fmt_usd(item.patient_responsibility)}",
                    ],
                    missing_data_points=missing_data_points,
                    **_appeal_deadline_fields(claim.visit_date),
                )
            )

    return opportunities


def _rule_upcoding_signal(claims: List[schemas.ClaimGroup]) -> List[schemas.SavingsOpportunity]:
    """
    Flag line items where the billed-to-allowed ratio is anomalously high.
    A ratio above 3.5x is a potential upcoding or fee-schedule error signal
    worth requesting provider justification for.
    """
    RATIO_THRESHOLD = 3.5
    MIN_BILLED = 300.0
    MIN_PATIENT_RESP = 50.0
    opportunities: List[schemas.SavingsOpportunity] = []

    for claim in claims:
        for item in claim.line_items:
            if item.allowed_amount <= 0 or item.billed_amount < MIN_BILLED:
                continue
            if item.patient_responsibility < MIN_PATIENT_RESP:
                continue
            # CO-45 items are expected to have high ratios — skip
            if item.reason_code and _normalize_carc_code(item.reason_code) == "CO-45":
                continue

            ratio = item.billed_amount / item.allowed_amount
            if ratio < RATIO_THRESHOLD:
                continue

            missing_data_points = [
                "CMS Medicare fee schedule rate for this CPT code and region",
                "Provider's explanation for billing above the allowed amount",
            ]
            score = _apply_data_confidence_guard(0.60, missing_data_points)

            # Savings = the portion of overcharge above the allowed amount that
            # the patient is actually bearing. min() caps it at their real
            # responsibility so we never overstate.
            overcharge = item.billed_amount - item.allowed_amount
            upcoding_savings = round(min(overcharge, item.patient_responsibility), 2)

            opportunities.append(
                schemas.SavingsOpportunity(
                    opportunity_id=str(uuid.uuid4()),
                    type="billing_error",
                    claim_id=claim.claim_id,
                    severity="medium",
                    estimated_savings=upcoding_savings,
                    description=(
                        f"Billed amount ({_fmt_usd(item.billed_amount)}) is {ratio:.1f}x the allowed amount "
                        f"({_fmt_usd(item.allowed_amount)}) for: {item.service_description}"
                    ),
                    recommended_action=(
                        "Request an itemized bill and ask the provider's billing office to justify the "
                        "billed-to-allowed ratio. Compare against the CMS Medicare fee schedule for this "
                        "service code at cms.gov/medicare/payment-systems."
                    ),
                    difficulty_level="medium",
                    time_estimate_days=21,
                    confidence_score=score,
                    confidence_level=_confidence_level(score),
                    flag_reason=f"Billed-to-allowed ratio of {ratio:.1f}x exceeds the expected range for typical claims.",
                    verification_steps=[
                        "Request an itemized bill from the provider with procedure (CPT) codes for each line.",
                        "Look up the CMS Medicare fee schedule for this CPT code at cms.gov.",
                        "If the allowed amount already reflects a fee-schedule rate, ask the provider why the billed amount is so far above it.",
                        "Ask provider billing: 'Can you explain the discrepancy between the billed and allowed amounts on this line?'",
                    ],
                    could_be_correct_if=[
                        "The procedure involved specialized equipment or unusually complex circumstances.",
                        "Multiple service components were bundled into a single line description.",
                        "The allowed amount reflects a deep contractual discount unrelated to Medicare rates.",
                    ],
                    evidence=[
                        f"Billed: {_fmt_usd(item.billed_amount)} / Allowed: {_fmt_usd(item.allowed_amount)} = {ratio:.1f}x ratio",
                        f"Service: {item.service_description}",
                    ],
                    missing_data_points=missing_data_points,
                    **_appeal_deadline_fields(claim.visit_date),
                )
            )

    return opportunities


def _rule_no_surprises_act(claims: List[schemas.ClaimGroup]) -> List[schemas.SavingsOpportunity]:
    """
    Detect out-of-network claims with emergency-care indicators that may be
    protected under the No Surprises Act (effective Jan 1, 2022). Under the NSA,
    out-of-network providers at in-network facilities generally cannot charge
    patients more than in-network cost-sharing for emergency services.
    """
    opportunities: List[schemas.SavingsOpportunity] = []

    for claim in claims:
        if claim.network_status != "out_of_network":
            continue
        if claim.total_patient_responsibility <= 100:
            continue

        text_to_scan = " ".join([
            claim.facility_name or "",
            claim.provider_name or "",
            *[item.service_description for item in claim.line_items],
        ]).lower()

        is_likely_emergency = any(kw in text_to_scan for kw in _NSA_EMERGENCY_KEYWORDS)
        if not is_likely_emergency:
            continue

        missing_data_points = [
            "Confirmation that the facility itself was in-network on the date of service",
            "Signed Notice and Consent waiver (if any) for this provider",
        ]
        score = _apply_data_confidence_guard(0.73, missing_data_points)

        opportunities.append(
            schemas.SavingsOpportunity(
                opportunity_id=str(uuid.uuid4()),
                type="balance_billing",
                claim_id=claim.claim_id,
                severity="critical",
                estimated_savings=round(claim.total_patient_responsibility * 0.70, 2),
                description=(
                    f"Out-of-network emergency service at {claim.facility_name or claim.provider_name} "
                    f"may be protected under the No Surprises Act. Patient responsibility of "
                    f"{_fmt_usd(claim.total_patient_responsibility)} may be reducible to in-network cost-sharing."
                ),
                recommended_action=(
                    "Under the No Surprises Act (effective Jan 2022), out-of-network providers at in-network "
                    "facilities cannot bill you more than in-network cost-sharing for emergency services. "
                    "Contact your insurer and ask them to reprocess this claim under NSA protections. "
                    "You can also file a complaint at cms.gov/nosurprises."
                ),
                difficulty_level="medium",
                time_estimate_days=30,
                confidence_score=score,
                confidence_level=_confidence_level(score),
                flag_reason="Out-of-network claim with emergency-service indicators may qualify for No Surprises Act patient protections.",
                verification_steps=[
                    "Confirm the facility (hospital or ER building) itself was in-network on the service date — call your insurer's provider directory.",
                    "Ask your insurer: 'Does the No Surprises Act apply to this claim?' and request a written response.",
                    "Check whether you signed a Notice and Consent form agreeing to out-of-network rates before the service.",
                    "If NSA applies, you should owe only your in-network deductible/coinsurance/copay — not the full out-of-network rate.",
                    "File a complaint at cms.gov/nosurprises if insurer refuses to apply NSA protections.",
                ],
                could_be_correct_if=[
                    "You received and signed a Notice and Consent form before service, voluntarily waiving NSA protections.",
                    "The facility itself (not just the provider) was also out-of-network.",
                    "The service was non-emergency scheduled care, not covered under NSA emergency provisions.",
                ],
                evidence=[
                    "Claim network_status is out_of_network",
                    "Service description contains emergency-care keywords",
                    f"Patient responsibility of {_fmt_usd(claim.total_patient_responsibility)} above NSA review threshold",
                ],
                missing_data_points=missing_data_points,
                **_appeal_deadline_fields(claim.visit_date),
            )
        )

    return opportunities




def _rule_duplicate_charge(claims: List[schemas.ClaimGroup]) -> List[schemas.SavingsOpportunity]:
    opportunities: List[schemas.SavingsOpportunity] = []
    service_descriptions = {}

    def _dup_key(visit_date: date, item: schemas.LineItem) -> tuple:
        """Match on CPT code + date when available; fall back to normalised description."""
        if item.cpt_code:
            return (visit_date, "cpt", item.cpt_code.strip().upper())
        return (visit_date, "desc", item.service_description.strip().lower())

    for claim in claims:
        for item in claim.line_items:
            key = _dup_key(claim.visit_date, item)
            if key not in service_descriptions:
                service_descriptions[key] = item
                continue

            missing_data_points = [
                "Provider billing correction notes",
                "Claim line-level remark codes",
            ]
            score = _apply_data_confidence_guard(0.86, missing_data_points)
            opportunities.append(
                schemas.SavingsOpportunity(
                    opportunity_id=str(uuid.uuid4()),
                    type="billing_error",
                    claim_id=claim.claim_id,
                    severity="high",
                    estimated_savings=item.billed_amount * 0.8,
                    description=f"Likely duplicate charge worth reviewing: {item.service_description}",
                    recommended_action="Contact insurance to dispute as duplicate charge. Provide dates and claim numbers.",
                    difficulty_level="easy",
                    time_estimate_days=14,
                    confidence_score=score,
                    confidence_level=_confidence_level(score),
                    flag_reason="A similar service appears more than once for the same visit window.",
                    verification_steps=[
                        "Confirm both line items were not separate procedures.",
                        "Ask provider billing office for itemized notes for each line.",
                        "Check insurer claim detail for duplicate denial/duplicate payment remark codes.",
                    ],
                    could_be_correct_if=[
                        "The service was repeated for medical necessity (for example, repeat imaging).",
                        "One line is a technical component and the other is a professional component.",
                    ],
                    evidence=[
                        "Matched service description appears multiple times for the same visit date",
                        "Billed amount pattern suggests potential duplicate billing",
                    ],
                    missing_data_points=missing_data_points,
                    **_appeal_deadline_fields(claim.visit_date),
                )
            )

    return opportunities


def _rule_out_of_network(claims: List[schemas.ClaimGroup]) -> List[schemas.SavingsOpportunity]:
    opportunities: List[schemas.SavingsOpportunity] = []

    for claim in claims:
        network_status = getattr(claim, "network_status", "unknown")
        network_confidence = getattr(claim, "network_confidence", "low")

        if claim.total_patient_responsibility <= 0:
            continue

        # Only fire when network status is explicitly out-of-network AND we have
        # high confidence in that determination. Text-based detection (medium) is
        # not sufficient — EOB fine print commonly references out-of-network coverage
        # even for in-network claims, which would cause false positives.
        if network_status != "out_of_network" or network_confidence != "high":
            continue

        # Yield to the more specific _rule_oon_referred_ancillary for lab / imaging /
        # anesthesia claims — those rules surface targeted action steps that are
        # more useful than the generic OON guidance here.
        service_text = " ".join([
            claim.facility_name or "",
            claim.provider_name or "",
            *[item.service_description for item in claim.line_items],
        ]).lower()
        if any(kw in service_text for kw in _REFERRED_ANCILLARY_KEYWORDS):
            continue

        missing_data_points = [
            "Current deductible met amount",
            "Out-of-pocket accumulator status",
            "Plan-specific out-of-network benefit design",
            "Emergency stabilization coding context",
        ]
        score = _apply_data_confidence_guard(0.7, missing_data_points)
        opportunities.append(
            schemas.SavingsOpportunity(
                opportunity_id=str(uuid.uuid4()),
                type="out_of_network",
                claim_id=claim.claim_id,
                severity="high",
                estimated_savings=claim.total_patient_responsibility * 0.5,
                description=f"Potential out-of-network balance billing worth reviewing at {claim.facility_name}",
                recommended_action="Contact facility to negotiate bill or request in-network rates. Ask about financial hardship programs.",
                difficulty_level="hard",
                time_estimate_days=30,
                confidence_score=score,
                confidence_level=_confidence_level(score),
                flag_reason="The claim is marked out-of-network and patient responsibility appears elevated vs allowed amount.",
                verification_steps=[
                    "Verify provider network status on the exact date of service.",
                    "Check whether the encounter qualifies under No Surprises protections.",
                    "Confirm deductible and out-of-pocket accumulators were applied correctly.",
                ],
                could_be_correct_if=[
                    "You intentionally used a non-participating provider.",
                    "Your plan has limited or no out-of-network benefits.",
                    "The service occurred before referral/prior authorization requirements were met.",
                ],
                evidence=[
                    "Claim network status is explicitly out_of_network",
                    "Patient responsibility is elevated relative to allowed amount",
                ],
                missing_data_points=missing_data_points,
                **_appeal_deadline_fields(claim.visit_date),
            )
        )

    return opportunities


# Service categories where the patient typically has no practical choice of
# provider because the service was ordered/referred by another clinician.
_REFERRED_ANCILLARY_KEYWORDS = [
    "laboratory", "lab service", "lab test", "pathology", "pathological",
    "radiology", "radiological", "imaging", "x-ray", "xray", "mri", "ct scan",
    "ultrasound", "nuclear medicine", "pet scan", "mammogram",
    "anesthesia", "anesthesiology",
    "assistant surgeon", "surgical assistant",
]


def _rule_oon_referred_ancillary(claims: List[schemas.ClaimGroup]) -> List[schemas.SavingsOpportunity]:
    """
    Detect OON charges for referred/ancillary services where the patient had
    no practical choice of provider (labs, imaging, pathology, anesthesia).
    These are among the strongest grounds for an in-network exception request
    because the patient could not have reasonably shopped for an in-network
    alternative at the time of service.

    Suppressed if _rule_no_surprises_act already fires (emergency pathway).
    """
    opportunities: List[schemas.SavingsOpportunity] = []

    for claim in claims:
        if claim.network_status != "out_of_network":
            continue
        if claim.total_patient_responsibility <= 50:
            continue
        # Require explicit high-confidence OON detection — medium confidence means the
        # OON signal came from body text / disclaimers and may be unreliable.
        if getattr(claim, "network_confidence", "low") != "high":
            continue

        service_text = " ".join([
            claim.facility_name or "",
            claim.provider_name or "",
            *[item.service_description for item in claim.line_items],
        ]).lower()

        is_referred_ancillary = any(kw in service_text for kw in _REFERRED_ANCILLARY_KEYWORDS)
        if not is_referred_ancillary:
            continue

        # Skip if the NSA emergency rule already covers this claim — don't duplicate.
        is_emergency = any(kw in service_text for kw in _NSA_EMERGENCY_KEYWORDS)
        if is_emergency:
            continue

        # 3 missing points (not 4): this rule already requires network_confidence="high"
        # (a labeled status field — not body text), so the OON status itself is certain.
        # The remaining unknowns are about the appeal argument strength, not the opportunity.
        # 3 missing points keeps base 0.68 uncapped → score=0.68 → confidence="medium".
        missing_data_points = [
            "Ordering provider name (who referred/ordered the service)",
            "Whether the referring provider is in-network",
            "Date the OON provider's contract with your insurer was terminated",
        ]
        score = _apply_data_confidence_guard(0.68, missing_data_points)

        opportunities.append(
            schemas.SavingsOpportunity(
                opportunity_id=str(uuid.uuid4()),
                type="out_of_network",
                claim_id=claim.claim_id,
                severity="high",
                estimated_savings=round(claim.total_patient_responsibility * 0.65, 2),
                description=(
                    f"Out-of-network charge for referred service at {claim.facility_name or claim.provider_name} "
                    f"— patient likely had no practical choice of provider."
                ),
                recommended_action=(
                    "Call your insurer and request an in-network exception for referred/ancillary services. "
                    "State that (1) the service was ordered by your treating provider, not self-selected; "
                    "(2) you had no reasonable opportunity to choose an in-network alternative; and "
                    "(3) you were unaware the provider had left the network. Ask them to reprocess "
                    "the claim at in-network cost-sharing rates."
                ),
                difficulty_level="medium",
                time_estimate_days=45,
                confidence_score=score,
                confidence_level=_confidence_level(score),
                flag_reason=(
                    "Out-of-network ancillary or referred service — patient had limited or no ability "
                    "to select an in-network provider. Insurers frequently grant exceptions for these."
                ),
                verification_steps=[
                    "Call the member services number on your insurance card and ask for an 'in-network exception' "
                    "or 'same-as-in-network' exception for this claim. Reference the claim number.",
                    "Ask your insurer: 'Was this provider in-network on the date of service, and if not, "
                    "when was their contract terminated?' — if the contract was recently terminated, you "
                    "may not have had any reasonable way to know.",
                    "Ask your ordering provider (the doctor who referred you) to write a brief letter "
                    "confirming they directed you to this facility — this strengthens the exception request.",
                    "If your insurer denies the exception, request a formal internal appeal. Cite that "
                    "you had no meaningful ability to choose an in-network provider for an ordered service.",
                    "If the appeal is denied, file a complaint with your state insurance commissioner. "
                    "Many states require insurers to hold patients harmless for inadvertent OON use "
                    "of referred ancillary services.",
                    "For future visits, call your insurer's provider directory line before any lab, "
                    "imaging, or ancillary service to verify the facility is still in-network — "
                    "network contracts change frequently.",
                ],
                could_be_correct_if=[
                    "You were informed before the service that the provider was out-of-network and agreed.",
                    "Your plan has no out-of-network benefits at all (HMO without OON coverage).",
                    "You self-referred to this provider without a clinical referral.",
                ],
                evidence=[
                    "Claim network_status is out_of_network",
                    "Service type is lab, imaging, pathology, or other referred ancillary category",
                    f"Patient responsibility of {_fmt_usd(claim.total_patient_responsibility)} is above review threshold",
                ],
                missing_data_points=missing_data_points,
                **_appeal_deadline_fields(claim.visit_date),
            )
        )

    return opportunities


def _rule_denied_claim_appeal(claims: List[schemas.ClaimGroup]) -> List[schemas.SavingsOpportunity]:
    opportunities: List[schemas.SavingsOpportunity] = []

    for claim in claims:
        denied_items = [item for item in claim.line_items if item.status == "denied"]
        for item in denied_items:
            if item.billed_amount <= 100:
                continue
            # Skip items already handled by _rule_reason_code_analysis to avoid duplicates
            if _get_carc_data(item.reason_code) is not None:
                continue
            # Skip hard plan exclusions — "plan does not cover" denials are contract
            # exclusions, not administrative errors, and appeals rarely succeed.
            if item.notes == "plan_exclusion":
                continue
            # Skip items where the patient owes nothing — no financial recovery possible.
            if item.patient_responsibility <= 0:
                continue

            missing_data_points = [
                "Full denial reason detail from insurer",
                "Prior authorization status",
                "Clinical documentation proving medical necessity",
            ]
            # Use a slightly higher default for unknown-reason denials — they often lack
            # a hard exclusion and are worth pursuing
            score = _apply_data_confidence_guard(0.62, missing_data_points)
            opportunities.append(
                schemas.SavingsOpportunity(
                    opportunity_id=str(uuid.uuid4()),
                    type="appeal",
                    claim_id=claim.claim_id,
                    severity="medium",
                    estimated_savings=round(item.patient_responsibility * 0.6, 2),
                    description=f"Denied claim may be appealable: {item.service_description}",
                    recommended_action="Request a full explanation of benefits with the denial reason code. Submit an appeal with medical necessity documentation from your provider.",
                    difficulty_level="medium",
                    time_estimate_days=45,
                    confidence_score=score,
                    confidence_level=_confidence_level(score),
                    flag_reason="Claim line is denied with financial impact high enough to justify appeal review.",
                    verification_steps=[
                        "Pull the complete denial code explanation from your insurer's member portal.",
                        "Validate that authorization and referral requirements were met.",
                        "Collect chart notes and a provider letter supporting medical necessity.",
                        "Note the appeal deadline — most plans require appeals within 180 days of denial.",
                    ],
                    could_be_correct_if=[
                        "The service is explicitly excluded by your plan documents.",
                        "Filing deadlines or authorization rules were not met.",
                    ],
                    evidence=[
                        "At least one line item is denied",
                        "Denied line billed amount is above review threshold",
                    ],
                    missing_data_points=missing_data_points,
                    **_appeal_deadline_fields(claim.visit_date),
                )
            )

    return opportunities


def _rule_unbundling(claims: List[schemas.ClaimGroup]) -> List[schemas.SavingsOpportunity]:
    """
    CCI (Correct Coding Initiative) unbundling detection.
    When both CPT codes of a CCI edit pair appear on the same claim,
    the component code is already included in the comprehensive code
    and should not be billed separately.
    Requires cpt_code field on LineItem to operate; claims without CPT codes are skipped.
    """
    opportunities: List[schemas.SavingsOpportunity] = []

    for claim in claims:
        # Map CPT code → line items for that code
        cpt_to_items: dict = {}
        for item in claim.line_items:
            if item.cpt_code:
                key = item.cpt_code.strip().upper()
                cpt_to_items.setdefault(key, []).append(item)

        if len(cpt_to_items) < 2:
            continue

        for comp_code, component_code, reason in CCI_EDIT_PAIRS:
            if comp_code not in cpt_to_items or component_code not in cpt_to_items:
                continue

            component_items = cpt_to_items[component_code]

            # If any component item carries a bypass modifier (-59, XU, XE, XP, XS) the
            # provider is asserting a distinct service.  Hand off to _rule_modifier_abuse
            # which fires a lower-confidence flag asking the consumer to verify.
            if any(_has_bypass_modifier(item.modifier) for item in component_items):
                continue

            component_billed = sum(item.billed_amount for item in component_items)

            missing_data_points = [
                "Modifier -59 or X-modifier documentation (may legitimately allow separate billing)",
                "Operative note confirming distinct service or separate anatomical site",
            ]
            score = _apply_data_confidence_guard(0.74, missing_data_points)
            opportunities.append(
                schemas.SavingsOpportunity(
                    opportunity_id=str(uuid.uuid4()),
                    type="billing_error",
                    claim_id=claim.claim_id,
                    severity="high",
                    estimated_savings=component_billed * 0.85,
                    description=(
                        f"Possible CCI unbundling: CPT {comp_code} (comprehensive) and "
                        f"CPT {component_code} (component) appear on the same claim."
                    ),
                    recommended_action=(
                        f"Request an itemized bill and verify whether modifier -59 is present on CPT {component_code}. "
                        f"If no modifier: ask your provider billing office to remove the component code and resubmit. "
                        f"The insurer should automatically include {component_code} in the allowance for {comp_code}."
                    ),
                    difficulty_level="medium",
                    time_estimate_days=21,
                    confidence_score=score,
                    confidence_level=_confidence_level(score),
                    flag_reason=reason,
                    verification_steps=[
                        f"Obtain itemized bill confirming both CPT {comp_code} and CPT {component_code} are listed.",
                        "Check whether modifier -59, XU, XE, XP, or XS is appended to the component code.",
                        "If no modifier: contact provider billing and request removal of the component code.",
                        "If modifier is present and services were distinct: document clearly for insurer review.",
                    ],
                    could_be_correct_if=[
                        "Modifier -59 or an X-modifier is attached confirming a distinct procedural service.",
                        "Services were performed at separate anatomical sites or in different operative sessions.",
                    ],
                    evidence=[
                        f"CPT {comp_code} (comprehensive) and CPT {component_code} (component) both found on claim {claim.claim_id}",
                        f"CMS CCI edit prohibits separate billing of {component_code} when {comp_code} is also billed",
                    ],
                    missing_data_points=missing_data_points,
                    **_appeal_deadline_fields(claim.visit_date),
                )
            )

    return opportunities


def _rule_coordination_of_benefits(claims: List[schemas.ClaimGroup]) -> List[schemas.SavingsOpportunity]:
    """
    Coordination of Benefits (COB) cross-claim pattern detection.
    When CO-22 appears on 2 or more distinct claims it signals a systemic
    payer-order dispute rather than an isolated denial.
    Single-claim CO-22 is already handled by _rule_reason_code_analysis.
    """
    opportunities: List[schemas.SavingsOpportunity] = []

    co22_claims = [
        claim for claim in claims
        if any(
            _normalize_carc_code(item.reason_code or "") == "CO-22"
            for item in claim.line_items
        )
    ]

    if len(co22_claims) < 2:
        return opportunities

    affected_ids = [c.claim_id for c in co22_claims]
    total_at_risk = sum(
        item.patient_responsibility
        for claim in co22_claims
        for item in claim.line_items
        if _normalize_carc_code(item.reason_code or "") == "CO-22"
    )

    missing_data_points = [
        "Secondary insurance policy details",
        "COB determination letter from primary insurer",
    ]
    score = _apply_data_confidence_guard(0.68, missing_data_points)
    opportunities.append(
        schemas.SavingsOpportunity(
            opportunity_id=str(uuid.uuid4()),
            type="coordination_of_benefits",
            claim_id=co22_claims[0].claim_id,
            severity="high",
            estimated_savings=total_at_risk * 0.70,
            description=(
                f"CO-22 (Coordination of Benefits) appears on {len(co22_claims)} separate claims "
                f"({', '.join(affected_ids)}), indicating a systemic payer-order dispute."
            ),
            recommended_action=(
                "Contact your insurer's COB department and request a formal COB determination letter. "
                "If you have only one active policy, submit written confirmation. "
                "If you have dual coverage, verify primary/secondary order with both insurers and "
                "refile denied claims with the correct primary payer. "
                "A single COB resolution typically corrects all affected claims at once."
            ),
            difficulty_level="medium",
            time_estimate_days=21,
            confidence_score=score,
            confidence_level=_confidence_level(score),
            flag_reason=(
                f"CO-22 (COB dispute) detected on {len(co22_claims)} claims — "
                "systemic pattern, not an isolated denial."
            ),
            verification_steps=[
                "List all EOBs with CO-22 and collect claim numbers and service dates.",
                "Confirm with your employer HR or insurance broker whether dual coverage exists.",
                "Request a COB determination letter from your primary insurer.",
                "Resubmit affected claims to the correct primary payer once COB order is confirmed.",
            ],
            could_be_correct_if=[
                "You were covered under two insurance plans during the service dates.",
                "A prior insurance plan was still active and should have been billed first.",
            ],
            evidence=[
                f"CO-22 found on claims: {', '.join(affected_ids)}",
                f"Total patient responsibility at risk: {_fmt_usd(total_at_risk)}",
            ],
            missing_data_points=missing_data_points,
            **_appeal_deadline_fields(co22_claims[0].visit_date),
        )
    )

    return opportunities


def _rule_systemic_prior_auth(claims: List[schemas.ClaimGroup]) -> List[schemas.SavingsOpportunity]:
    """
    Systemic prior-authorization failure cross-claim detection.

    When CO-197 (prior auth missing) or CO-57 (referral absent) appears on
    2 or more *distinct* claims — especially from the same or related providers —
    it signals a recurring failure in the provider's pre-authorization workflow,
    not a one-off patient error.  The actionable recommendation shifts from
    "appeal this denial" to "engage the provider billing department to correct
    their authorization process," which has a materially higher resolution rate.

    Single-claim CO-197/CO-57 is already handled by _rule_reason_code_analysis.
    """
    opportunities: List[schemas.SavingsOpportunity] = []

    prior_auth_codes = {"CO-197", "CO-57"}

    # Collect claims that have at least one CO-197 or CO-57 line item
    affected_claims = [
        claim for claim in claims
        if any(
            _normalize_carc_code(item.reason_code or "") in prior_auth_codes
            for item in claim.line_items
        )
    ]

    if len(affected_claims) < 2:
        return opportunities

    affected_ids = [c.claim_id for c in affected_claims]

    # Count distinct providers to sharpen the recommendation
    distinct_providers = {c.provider_name for c in affected_claims if c.provider_name}
    provider_note = (
        f"All denials are from a single provider ({next(iter(distinct_providers))}), "
        "strongly suggesting a recurring pre-authorization workflow failure at that practice."
        if len(distinct_providers) == 1
        else f"Denials span {len(distinct_providers)} providers, suggesting either a plan-wide "
        "authorization requirement change or a systemic referral tracking issue."
    )

    # Tally codes to surface the dominant pattern
    co197_count = sum(
        1 for claim in affected_claims
        for item in claim.line_items
        if _normalize_carc_code(item.reason_code or "") == "CO-197"
    )
    co57_count = sum(
        1 for claim in affected_claims
        for item in claim.line_items
        if _normalize_carc_code(item.reason_code or "") == "CO-57"
    )

    if co197_count >= co57_count:
        primary_code = "CO-197"
        primary_label = "prior authorization missing"
    else:
        primary_code = "CO-57"
        primary_label = "referral absent"

    total_at_risk = sum(
        item.patient_responsibility
        for claim in affected_claims
        for item in claim.line_items
        if _normalize_carc_code(item.reason_code or "") in prior_auth_codes
    )

    missing_data_points = [
        "Prior authorization request confirmation numbers from provider",
        "Plan authorization requirement documentation for each service type",
    ]
    score = _apply_data_confidence_guard(0.55, missing_data_points)

    opportunities.append(
        schemas.SavingsOpportunity(
            opportunity_id=str(uuid.uuid4()),
            type="appeal",
            claim_id=affected_claims[0].claim_id,
            severity="high",
            estimated_savings=round(total_at_risk * 0.50, 2),
            description=(
                f"Systemic prior-authorization failure detected: {primary_label} ({primary_code}) "
                f"appears on {len(affected_claims)} separate claims "
                f"({', '.join(affected_ids)}). {provider_note}"
            ),
            recommended_action=(
                "This pattern indicates a recurring workflow problem, not an isolated error. "
                "Contact the provider's billing or authorization department and request a written "
                "explanation of their pre-authorization process for these service types. "
                "Ask whether any retroactive authorization requests were submitted. "
                "For each denial, file a formal appeal citing provider administrative error and "
                "request the insurer apply retroactive authorization where medically appropriate. "
                "If the provider acknowledges the error, request they resubmit all affected claims "
                "with corrected authorization data before the appeal deadline."
            ),
            difficulty_level="hard",
            time_estimate_days=45,
            confidence_score=score,
            confidence_level=_confidence_level(score),
            flag_reason=(
                f"{primary_code} ({primary_label}) detected on {len(affected_claims)} claims — "
                "systemic pattern consistent with provider pre-authorization workflow failure."
            ),
            verification_steps=[
                f"Collect all EOBs showing {primary_code} and list service dates and providers.",
                "Contact the provider billing department and ask for the authorization request log "
                "for each affected service date.",
                "Request your insurer's written prior-authorization requirements for each service type.",
                "File a formal appeal for each claim citing provider administrative error and "
                "requesting retroactive authorization consideration.",
                "Set calendar reminders for each claim's appeal deadline — missing one forfeits "
                "that claim's recovery.",
            ],
            could_be_correct_if=[
                "Your plan genuinely requires prior authorization for these service types and "
                "the provider was informed.",
                "A retroactive authorization request was already denied and confirmed in writing.",
                "Services were elective and the patient acknowledged the authorization requirement "
                "in advance.",
            ],
            evidence=[
                f"{primary_code} ({primary_label}) found on claims: {', '.join(affected_ids)}",
                f"CO-197 occurrences: {co197_count} | CO-57 occurrences: {co57_count}",
                f"Total patient responsibility at risk: {_fmt_usd(total_at_risk)}",
                provider_note,
            ],
            missing_data_points=missing_data_points,
            **_appeal_deadline_fields(affected_claims[0].visit_date),
        )
    )

    return opportunities


def _rule_modifier_abuse(claims: List[schemas.ClaimGroup]) -> List[schemas.SavingsOpportunity]:
    """
    Modifier-based overbilling detection.

    Two patterns:

    1. CCI bypass with -59 / X-modifiers
       When a CCI edit pair is present on a claim AND the component code carries a
       bypass modifier (-59, XU, XE, XP, XS), the provider is asserting a distinct
       service to circumvent the CCI edit.  This is sometimes legitimate but is a
       documented abuse vector.  Lower-confidence flag asking the consumer to verify.
       (_rule_unbundling skips these pairs, so this rule is the only one that fires.)

    2. Modifier -25 on same-day E/M + procedure
       Modifier -25 on an E/M code (CPT 99202-99499) indicates a "significant,
       separately identifiable evaluation and management service" on the same day as
       a procedure.  It is frequently misapplied to collect a full office-visit fee
       for pre-procedure work that is already bundled into the procedure's RVU.
    """
    opportunities: List[schemas.SavingsOpportunity] = []

    for claim in claims:
        cpt_to_items: dict = {}
        for item in claim.line_items:
            if item.cpt_code:
                key = item.cpt_code.strip().upper()
                cpt_to_items.setdefault(key, []).append(item)

        # ------------------------------------------------------------------
        # Pattern 1: -59 / X-modifier bypass of a CCI edit pair
        # ------------------------------------------------------------------
        for comp_code, component_code, cci_reason in CCI_EDIT_PAIRS:
            if comp_code not in cpt_to_items or component_code not in cpt_to_items:
                continue
            component_items = cpt_to_items[component_code]
            if not any(_has_bypass_modifier(item.modifier) for item in component_items):
                continue  # No bypass modifier — already handled by _rule_unbundling

            bypass_item = next(i for i in component_items if _has_bypass_modifier(i.modifier))
            modifier_used = bypass_item.modifier or "-59"
            component_billed = sum(item.billed_amount for item in component_items)

            missing_data_points = [
                "Operative or clinical note confirming a distinct anatomical site or separate service session",
                "Provider documentation explaining why the bypass modifier is clinically justified",
            ]
            score = _apply_data_confidence_guard(0.45, missing_data_points)
            opportunities.append(
                schemas.SavingsOpportunity(
                    opportunity_id=str(uuid.uuid4()),
                    type="billing_error",
                    claim_id=claim.claim_id,
                    severity="medium",
                    estimated_savings=component_billed * 0.70,
                    description=(
                        f"Modifier {modifier_used} applied to CPT {component_code} alongside "
                        f"CPT {comp_code} (comprehensive code). Modifier -59 and X-modifiers are "
                        f"used to override CCI edit pairs; they are sometimes legitimate but are "
                        f"a documented overbilling method."
                    ),
                    recommended_action=(
                        f"Request the itemized bill and ask the provider to supply the clinical note "
                        f"justifying modifier {modifier_used} on CPT {component_code}. "
                        f"The note must document a distinct service at a separate anatomical site or "
                        f"a separate operative session — not routine pre/post-procedure work. "
                        f"If no such documentation exists, ask the provider to remove the modifier and "
                        f"resubmit; the insurer should then bundle {component_code} into {comp_code}."
                    ),
                    difficulty_level="medium",
                    time_estimate_days=21,
                    confidence_score=score,
                    confidence_level=_confidence_level(score),
                    flag_reason=(
                        f"Modifier {modifier_used} on CPT {component_code} used to bypass CCI edit with "
                        f"CPT {comp_code} — verify clinical justification."
                    ),
                    verification_steps=[
                        f"Obtain itemized bill confirming CPT {comp_code}, CPT {component_code}, "
                        f"and modifier {modifier_used}.",
                        "Ask the provider: 'Can you provide the clinical note showing why a distinct "
                        f"service justifies modifier {modifier_used} on CPT {component_code}?'",
                        "If documentation is absent or insufficient, request the modifier be removed "
                        "and the claim resubmitted.",
                        "If the provider cannot justify the modifier, escalate to your insurer asking "
                        "them to reprocess and bundle the component code.",
                    ],
                    could_be_correct_if=[
                        "The service was performed at a separate anatomical site in the same session.",
                        "Two distinct procedures occurred on the same day in separate operative sessions.",
                        "The provider has complete documentation satisfying the modifier's clinical criteria.",
                    ],
                    evidence=[
                        f"CPT {comp_code} (comprehensive) billed alongside CPT {component_code} "
                        f"(component) with modifier {modifier_used} on claim {claim.claim_id}",
                        cci_reason,
                    ],
                    missing_data_points=missing_data_points,
                    **_appeal_deadline_fields(claim.visit_date),
                )
            )

        # ------------------------------------------------------------------
        # Pattern 2: Modifier -25 on E/M code same-day as procedure
        # ------------------------------------------------------------------
        em_items_with_25 = [
            item for item in claim.line_items
            if item.cpt_code
            and _is_em_cpt(item.cpt_code)
            and "25" in _parse_modifiers(item.modifier)
        ]
        non_em_procedure_items = [
            item for item in claim.line_items
            if item.cpt_code and not _is_em_cpt(item.cpt_code)
        ]

        if not em_items_with_25 or not non_em_procedure_items:
            continue

        for em_item in em_items_with_25:
            em_billed = em_item.billed_amount
            procedure_codes = ", ".join(
                sorted({i.cpt_code.strip().upper() for i in non_em_procedure_items if i.cpt_code})
            )

            missing_data_points = [
                "Documentation confirming the E/M addressed a separate, significant medical condition "
                "unrelated to the procedure performed",
                "Provider's modifier -25 attestation or clinical note",
            ]
            score = _apply_data_confidence_guard(0.50, missing_data_points)
            opportunities.append(
                schemas.SavingsOpportunity(
                    opportunity_id=str(uuid.uuid4()),
                    type="billing_error",
                    claim_id=claim.claim_id,
                    severity="medium",
                    estimated_savings=em_billed * 0.80,
                    description=(
                        f"Modifier -25 on E/M code CPT {em_item.cpt_code.strip().upper()} same day as "
                        f"procedure(s) {procedure_codes}. Modifier -25 is meant for a 'significant, "
                        f"separately identifiable' evaluation — not routine pre-procedure counseling "
                        f"already bundled into the procedure's payment."
                    ),
                    recommended_action=(
                        f"Ask the provider to supply the clinical note showing the E/M (CPT "
                        f"{em_item.cpt_code.strip().upper()}) addressed a distinct, significant condition "
                        f"separate from the reason for the procedure. "
                        f"If the note only documents standard pre-procedure evaluation, ask the provider "
                        f"to remove the -25 modifier and resubmit — the E/M is already bundled into the "
                        f"procedure's reimbursement. "
                        f"Your insurer can also flag this for review by calling member services and "
                        f"referencing the claim number."
                    ),
                    difficulty_level="medium",
                    time_estimate_days=21,
                    confidence_score=score,
                    confidence_level=_confidence_level(score),
                    flag_reason=(
                        f"Modifier -25 on E/M CPT {em_item.cpt_code.strip().upper()} billed same day "
                        f"as procedure(s) {procedure_codes} — common overbilling pattern."
                    ),
                    verification_steps=[
                        f"Confirm CPT {em_item.cpt_code.strip().upper()} and procedure code(s) "
                        f"{procedure_codes} appear on the same claim.",
                        "Ask the provider billing office: 'What separate, significant condition was "
                        "addressed in the office visit that is distinct from the procedure?'",
                        "Request the clinical note documenting the E/M service and verify it describes "
                        "a problem unrelated to the procedure.",
                        "If the E/M was routine pre-procedure work, request removal of modifier -25 "
                        "and resubmission.",
                    ],
                    could_be_correct_if=[
                        "The provider evaluated and managed a separate, significant medical condition "
                        "during the same encounter (e.g., managing hypertension during a minor procedure visit).",
                        "The clinical note clearly documents the distinct E/M service.",
                        "Your insurer already reviewed and confirmed the modifier is appropriate.",
                    ],
                    evidence=[
                        f"E/M CPT {em_item.cpt_code.strip().upper()} with modifier -25 billed "
                        f"alongside procedure(s) {procedure_codes} on claim {claim.claim_id}",
                        f"E/M billed amount: {_fmt_usd(em_billed)}",
                    ],
                    missing_data_points=missing_data_points,
                    **_appeal_deadline_fields(claim.visit_date),
                )
            )

    return opportunities
