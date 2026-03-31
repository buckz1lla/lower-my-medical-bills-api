import uuid
from typing import List

from app import schemas


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


def evaluate_claims(claims: List[schemas.ClaimGroup]) -> List[schemas.SavingsOpportunity]:
    """Run all active rules and return savings opportunities."""
    opportunities: List[schemas.SavingsOpportunity] = []

    opportunities.extend(_rule_duplicate_charge(claims))
    opportunities.extend(_rule_out_of_network(claims))
    opportunities.extend(_rule_denied_claim_appeal(claims))

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

            missing_data_points = [
                "Full denial reason detail from insurer",
                "Prior authorization status",
                "Clinical documentation proving medical necessity",
            ]
            score = _apply_data_confidence_guard(0.68, missing_data_points)
            opportunities.append(
                schemas.SavingsOpportunity(
                    opportunity_id=str(uuid.uuid4()),
                    type="appeal",
                    claim_id=claim.claim_id,
                    severity="medium",
                    estimated_savings=item.billed_amount * 0.6,
                    description=f"Denied claim may be appealable: {item.service_description}",
                    recommended_action="Request explanation of benefits and submit appeal with medical necessity documentation.",
                    difficulty_level="medium",
                    time_estimate_days=45,
                    confidence_score=score,
                    confidence_level=_confidence_level(score),
                    flag_reason="Claim line is denied with financial impact high enough to justify appeal review.",
                    verification_steps=[
                        "Pull the complete denial code explanation from your insurer.",
                        "Validate that authorization/referral requirements were met.",
                        "Collect chart notes and provider letter supporting medical necessity.",
                    ],
                    could_be_correct_if=[
                        "The service is explicitly excluded by your plan documents.",
                        "Filing deadlines or authorization rules were not met.",
                    ],
                    missing_data_points=missing_data_points,
                )
            )

    return opportunities
