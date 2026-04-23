import re
import uuid
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
    "CO-22": {
        "explanation": "This care may be covered by another payer per coordination of benefits (COB). Insurer believes you have another insurance policy that should pay first.",
        "action": "If you have only one insurance plan, send your insurer written confirmation. If you have dual coverage, verify the correct primary/secondary payer order with both insurers. File with the correct primary payer first.",
        "success_probability": 0.58,
        "difficulty_level": "medium",
        "time_estimate_days": 21,
        "severity": "medium",
        "category": "billing_error",
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
}

# Emergency service keywords for No Surprises Act detection
_NSA_EMERGENCY_KEYWORDS = [
    "emergency", "emergent", "er visit", "emergency room", "emergency dept",
    "emergency department", "urgent care", "stabilization", "ambulance",
    "ems", "trauma", "critical care", "emergency services",
]


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
    opportunities.extend(_rule_no_surprises_act(claims))
    opportunities.extend(_rule_upcoding_signal(claims))
    opportunities.extend(_rule_denied_claim_appeal(claims))
    opportunities.extend(_rule_deductible_accumulator(claims, user_profile))

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

            opportunities.append(
                schemas.SavingsOpportunity(
                    opportunity_id=str(uuid.uuid4()),
                    type="billing_error",
                    claim_id=claim.claim_id,
                    severity="medium",
                    estimated_savings=round(item.patient_responsibility * 0.5, 2),
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
            )
        )

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
                )
            )

    return opportunities


def _rule_duplicate_charge(claims: List[schemas.ClaimGroup]) -> List[schemas.SavingsOpportunity]:
    opportunities: List[schemas.SavingsOpportunity] = []
    service_descriptions = {}

    for claim in claims:
        for item in claim.line_items:
            key = (claim.visit_date, item.service_description)
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

        # Safety guard: only raise out-of-network opportunities when status is explicit.
        if network_status != "out_of_network" or network_confidence == "low":
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
                    estimated_savings=item.billed_amount * 0.6,
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
                )
            )

    return opportunities
