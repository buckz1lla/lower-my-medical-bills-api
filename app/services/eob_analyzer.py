import uuid
from datetime import date, datetime
from typing import List
from app import schemas
import json

# Simulated database of common billing errors and patterns
COMMON_BILLING_ERRORS = {
    "duplicate_charge": {
        "pattern": "Same service billed multiple times",
        "savings_potential": 0.8,
        "difficulty": "easy"
    },
    "incorrect_coding": {
        "pattern": "Procedure coded incorrectly leading to higher charges",
        "savings_potential": 0.7,
        "difficulty": "medium"
    },
    "balance_billing": {
        "pattern": "Out-of-network provider billing excess amounts",
        "savings_potential": 0.6,
        "difficulty": "hard"
    },
    "unbundling": {
        "pattern": "Procedures that should be bundled billed separately",
        "savings_potential": 0.75,
        "difficulty": "medium"
    }
}

async def analyze_eob(
    file_name: str,
    content: bytes,
    file_type: str,
    analysis_id: str
) -> schemas.EOBAnalysis:
    """
    Analyze an EOB file and identify savings opportunities.
    
    In production, this would:
    - Use OCR for PDFs/images
    - Parse CSV/Excel files
    - Call ML models to detect anomalies
    - Integrate with insurance databases
    """
    
    # For MVP, generate realistic demo data
    # In production, parse the actual file
    claims = _generate_demo_claims()
    
    # Analyze claims for opportunities
    savings_opportunities = _identify_savings_opportunities(claims)
    appeal_recommendations = _generate_appeal_recommendations(claims, savings_opportunities)
    
    # Calculate totals
    total_billed = sum(claim.total_billed for claim in claims)
    total_paid = sum(claim.total_paid_by_insurance for claim in claims)
    total_patient_resp = sum(claim.total_patient_responsibility for claim in claims)
    total_savings = sum(opp.estimated_savings for opp in savings_opportunities)
    
    # Build key metrics
    key_metrics = {
        "total_claims": len(claims),
        "in_network_claims": sum(1 for c in claims if c.in_network),
        "out_of_network_claims": sum(1 for c in claims if not c.in_network),
        "denied_claims": sum(1 for claim in claims for item in claim.line_items if item.status == "denied"),
        "billing_error_ratio": _calculate_error_ratio(claims),
        "oob_overpayment": _calculate_oob_overpayment(claims)
    }
    
    return schemas.EOBAnalysis(
        analysis_id=analysis_id,
        file_name=file_name,
        upload_date=date.today(),
        analysis_date=date.today(),
        claims=claims,
        total_billed=total_billed,
        total_paid_by_insurance=total_paid,
        total_patient_responsibility=total_patient_resp,
        total_potential_savings=total_savings,
        savings_opportunities=savings_opportunities,
        appeal_recommendations=appeal_recommendations,
        key_metrics=key_metrics
    )

def _generate_demo_claims() -> List[schemas.ClaimGroup]:
    """Generate realistic demo claims for MVP testing."""
    claims = [
        schemas.ClaimGroup(
            claim_id="CLM001",
            visit_date=date(2024, 1, 15),
            provider_name="City Hospital Emergency",
            provider_npi="1234567890",
            facility_name="City Hospital",
            line_items=[
                schemas.LineItem(
                    service_date=date(2024, 1, 15),
                    provider_name="City Hospital",
                    service_description="Emergency Room Visit",
                    billed_amount=2500.00,
                    allowed_amount=1200.00,
                    patient_responsibility=300.00,
                    insurance_paid=900.00,
                    status="partial",
                    reason_code="PARTIAL_APPROVAL"
                ),
                schemas.LineItem(
                    service_date=date(2024, 1, 15),
                    provider_name="City Hospital",
                    service_description="Chest X-Ray (appears to be duplicate)",
                    billed_amount=800.00,
                    allowed_amount=300.00,
                    patient_responsibility=150.00,
                    insurance_paid=150.00,
                    status="paid",
                    notes="This appears to be duplicate of earlier X-ray"
                )
            ],
            in_network=True,
            total_billed=3300.00,
            total_allowed=1500.00,
            total_paid_by_insurance=1050.00,
            total_patient_responsibility=450.00
        ),
        schemas.ClaimGroup(
            claim_id="CLM002",
            visit_date=date(2024, 2, 10),
            provider_name="Out of Network Clinic",
            provider_npi="0987654321",
            facility_name="Local Urgent Care",
            line_items=[
                schemas.LineItem(
                    service_date=date(2024, 2, 10),
                    provider_name="Out of Network Clinic",
                    service_description="Office Visit - Urgent Care",
                    billed_amount=500.00,
                    allowed_amount=150.00,
                    patient_responsibility=150.00,
                    insurance_paid=0.00,
                    status="denied",
                    reason_code="OUT_OF_NETWORK"
                )
            ],
            in_network=False,
            total_billed=500.00,
            total_allowed=150.00,
            total_paid_by_insurance=0.00,
            total_patient_responsibility=150.00
        ),
        schemas.ClaimGroup(
            claim_id="CLM003",
            visit_date=date(2024, 3, 5),
            provider_name="Dr. Smith Medical",
            provider_npi="1122334455",
            facility_name="Smith Medical Office",
            line_items=[
                schemas.LineItem(
                    service_date=date(2024, 3, 5),
                    provider_name="Dr. Smith",
                    service_description="Office Visit - New Patient",
                    billed_amount=250.00,
                    allowed_amount=120.00,
                    patient_responsibility=30.00,
                    insurance_paid=90.00,
                    status="paid"
                )
            ],
            in_network=True,
            total_billed=250.00,
            total_allowed=120.00,
            total_paid_by_insurance=90.00,
            total_patient_responsibility=30.00
        )
    ]
    return claims

def _identify_savings_opportunities(
    claims: List[schemas.ClaimGroup]
) -> List[schemas.SavingsOpportunity]:
    """Identify potential savings opportunities in claims."""
    opportunities = []

    def confidence_level(score: float) -> str:
        if score >= 0.8:
            return "high"
        if score >= 0.6:
            return "medium"
        return "low"

    def apply_data_confidence_guard(raw_score: float, missing_data_points: List[str]) -> float:
        # When key plan-state fields are missing, downgrade certainty to avoid overconfident guidance.
        score = raw_score
        if len(missing_data_points) >= 3 and score > 0.69:
            score = 0.69
        if len(missing_data_points) >= 4 and score > 0.55:
            score = 0.55
        return round(score, 2)
    
    # Check for duplicate charges
    service_descriptions = {}
    for claim in claims:
        for item in claim.line_items:
            key = (claim.visit_date, item.service_description)
            if key in service_descriptions:
                opp_id = str(uuid.uuid4())
                missing_data_points = [
                    "Provider billing correction notes",
                    "Claim line-level remark codes",
                ]
                score = apply_data_confidence_guard(0.86, missing_data_points)
                opportunities.append(schemas.SavingsOpportunity(
                    opportunity_id=opp_id,
                    type="billing_error",
                    claim_id=claim.claim_id,
                    severity="high",
                    estimated_savings=item.billed_amount * 0.8,
                    description=f"Likely duplicate charge worth reviewing: {item.service_description}",
                    recommended_action="Contact insurance to dispute as duplicate charge. Provide dates and claim numbers.",
                    difficulty_level="easy",
                    time_estimate_days=14,
                    confidence_score=score,
                    confidence_level=confidence_level(score),
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
                ))
            else:
                service_descriptions[key] = item
    
    # Check for out-of-network issues
    for claim in claims:
        if not claim.in_network and claim.total_patient_responsibility > 0:
            opp_id = str(uuid.uuid4())
            missing_data_points = [
                "Current deductible met amount",
                "Out-of-pocket accumulator status",
                "Plan-specific out-of-network benefit design",
                "Emergency stabilization coding context",
            ]
            score = apply_data_confidence_guard(0.7, missing_data_points)
            opportunities.append(schemas.SavingsOpportunity(
                opportunity_id=opp_id,
                type="out_of_network",
                claim_id=claim.claim_id,
                severity="high",
                estimated_savings=claim.total_patient_responsibility * 0.5,
                description=f"Potential out-of-network balance billing worth reviewing at {claim.facility_name}",
                recommended_action="Contact facility to negotiate bill or request in-network rates. Ask about financial hardship programs.",
                difficulty_level="hard",
                time_estimate_days=30,
                confidence_score=score,
                confidence_level=confidence_level(score),
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
            ))
    
    # Check for denied claims that might be appealable
    for claim in claims:
        denied_items = [item for item in claim.line_items if item.status == "denied"]
        if denied_items:
            for item in denied_items:
                if item.billed_amount > 100:  # Only flag significant amounts
                    opp_id = str(uuid.uuid4())
                    missing_data_points = [
                        "Full denial reason detail from insurer",
                        "Prior authorization status",
                        "Clinical documentation proving medical necessity",
                    ]
                    score = apply_data_confidence_guard(0.68, missing_data_points)
                    opportunities.append(schemas.SavingsOpportunity(
                        opportunity_id=opp_id,
                        type="appeal",
                        claim_id=claim.claim_id,
                        severity="medium",
                        estimated_savings=item.billed_amount * 0.6,
                        description=f"Denied claim may be appealable: {item.service_description}",
                        recommended_action="Request explanation of benefits and submit appeal with medical necessity documentation.",
                        difficulty_level="medium",
                        time_estimate_days=45,
                        confidence_score=score,
                        confidence_level=confidence_level(score),
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
                    ))
    
    return opportunities

def _generate_appeal_recommendations(
    claims: List[schemas.ClaimGroup],
    opportunities: List[schemas.SavingsOpportunity]
) -> List[schemas.AppealRecommendation]:
    """Generate appeal recommendations for claims."""
    recommendations = []
    
    # Filter to appeal-type opportunities
    appeal_opps = [opp for opp in opportunities if opp.type == "appeal"]
    
    for opp in appeal_opps:
        # Find the claim
        claim = next((c for c in claims if c.claim_id == opp.claim_id), None)
        if not claim:
            continue
        
        rec = schemas.AppealRecommendation(
            claim_id=opp.claim_id,
            reason=f"Claim denied: {opp.description}",
            success_probability=0.65,
            steps=[
                "Request Explanation of Benefits (EOB) if not received",
                "Gather medical records and documentation supporting medical necessity",
                "Submit formal appeal to insurance with supporting documents",
                "Follow up if no response within 30 days",
                "Request external review if appeal is denied"
            ],
            contact_info={
                "provider_name": claim.provider_name,
                "appeals_department": "See EOB or insurance website for appeals details"
            }
        )
        recommendations.append(rec)
    
    return recommendations

def _calculate_error_ratio(claims: List[schemas.ClaimGroup]) -> float:
    """Calculate the ratio of denied/partial claims."""
    total_claims = len(claims)
    if total_claims == 0:
        return 0.0
    
    problematic = sum(
        1 for claim in claims 
        for item in claim.line_items 
        if item.status in ["denied", "partial"]
    )
    
    return problematic / total_claims

def _calculate_oob_overpayment(claims: List[schemas.ClaimGroup]) -> float:
    """Calculate potential overpayment from out-of-network claims."""
    total = 0.0
    for claim in claims:
        if not claim.in_network:
            # Out-of-network might have balance billing
            total += (claim.total_billed - claim.total_allowed) * 0.5
    return total


# Template Generation for Appeal Packages
def generate_appeal_templates(analysis: schemas.EOBAnalysis) -> dict:
    """
    Generate personalized appeal letter, scripts, and checklist
    based on analysis findings.
    """
    templates = {
        "appeal_letter": _generate_appeal_letter(analysis),
        "phone_script_insurer": _generate_insurer_script(analysis),
        "phone_script_provider": _generate_provider_script(analysis),
        "appeal_checklist": _generate_appeal_checklist(analysis),
        "negotiation_talking_points": _generate_talking_points(analysis)
    }
    return templates


def _generate_appeal_letter(analysis: schemas.EOBAnalysis) -> str:
    """Generate formal appeal letter template."""
    letter = f"""
FORMAL INSURANCE APPEAL LETTER

[Your Name]
[Your Address]
[Date]

[Insurance Company Name]
Appeals Department
[Mailing Address from EOB]

Re: Formal Appeal of Claim Denial
Member ID: [Your Member ID]
Claim Number(s): {', '.join(set(c.claim_id for c in analysis.claims))}
Date of Service: {analysis.claims[0].visit_date.strftime('%B %d, %Y') if analysis.claims else '[Date]'}

Dear Appeals Review Team,

I am writing to formally appeal the denial of my insurance claim(s) as noted above.

REASON FOR APPEAL:
Based on my review of the Explanation of Benefits, I believe these claims were incorrectly denied for the following reasons:

1. Medical Necessity: The services rendered were medically necessary and appropriate for my condition.
2. Plan Coverage: The services provided are covered benefits under my plan.
3. Network Status: [If applicable] The provider was in-network at the time of service.

SUPPORTING FACTS:
- Total billed amount: ${analysis.total_billed:,.2f}
- Insurance allowable: ${sum(c.total_allowed for c in analysis.claims):,.2f}
- Out-of-pocket cost to me: ${analysis.total_patient_responsibility:,.2f}

REQUESTED ACTION:
I respectfully request that you reconsider this denial and approve the claim for payment.

Enclosed please find supporting documentation:
_ Copy of Explanation of Benefits
_ Medical records from provider
_ Letter from physician explaining medical necessity
_ Contract details showing coverage for this service

Please respond within 30 days of receipt. If this appeal is not successful, I will request external review.

Sincerely,

[Your Signature]
[Your Typed Name]
[Phone Number]
[Email]
"""
    return letter


def _generate_insurer_script(analysis: schemas.EOBAnalysis) -> str:
    """Generate phone script for calling insurance company."""
    script = f"""
PHONE SCRIPT FOR INSURANCE COMPANY

Opening (when representative answers):
"Hello, I'm calling about a claim that was denied. My member ID is [your ID]. 
Can you help me understand why claim number [claim #] was denied?"

For each issue:
1. DUPLICATE CHARGES:
   "I've reviewed my Explanation of Benefits and I believe I was billed twice for the same service 
   on [date]. The claim shows [service description] appearing on lines [numbers]. 
   Can you help me understand why I'm being charged twice for one service?"

2. OUT-OF-NETWORK DENIAL:
   "I received an out-of-network denial, but [provider name] was in-network at the time of service. 
   Can you verify the in-network status as of [date of service]? I have documentation showing 
   they were in-network."

3. GENERAL DENIAL:
   "The denial code shows [reason code]. Can you explain what this means and what specific 
   documentation you need to overturn this denial? I have medical records from my provider 
   proving medical necessity."

Closing:
"Thank you for the explanation. Can I follow this appeal process in writing? 
I'll be sending a formal appeal with supporting documents to your appeals department. 
Can you confirm the correct mailing address and any fax number I should use?"

Key Points:
* Stay calm and professional
* Acknowledge the representative
* Ask clarifying questions
* Get a name and direct number
* Ask for confirmation in writing
* Don't accept "final decision" on first call
"""
    return script


def _generate_provider_script(analysis: schemas.EOBAnalysis) -> str:
    """Generate phone script for provider/facility."""
    script = f"""
PHONE SCRIPT FOR PROVIDER/FACILITY

Situation: Total amount billed vs. insurance payment creates a balance.

Opening:
"Hi, I'm calling about a bill I received from [facility name]. The claim number is [#], 
and I'm concerned about the balance I'm being asked to pay."

Main points:
1. "According to my insurance, the allowed amount for this service is $[amount]. 
   Why am I being charged $[difference] more?"

2. "Can you verify this provider was in-network with my insurance on [date of service]?"

3. "Insurance paid the negotiated rate. I shouldn't be responsible for balancing billing charges."

If out-of-network:
4. "I was told this facility was in-network. If that's changed, why wasn't I notified before treatment?"

5. "I'm requesting either: (a) write-off of the balance, or (b) 
   a payment plan for a reduced amount."

If denied:
6. "The claim was denied by insurance. Rather than billing me, can you help me appeal this?"

Closing:
"I want to resolve this fairly. Can you:"
- Check for any outstanding appeals?
- Offer a reduced/settlement amount?
- Delay billing while I handle the insurance appeal?

Get contact: "Can I get your supervisor's name? I'll follow up in writing if we can't resolve this today."
"""
    return script


def _generate_appeal_checklist(analysis: schemas.EOBAnalysis) -> str:
    """Generate action checklist for appeals."""
    checklist = f"""
APPEAL ACTION CHECKLIST

IMMEDIATE ACTIONS (This Week):
[ ] Gather your insurance paperwork and EOB
[ ] Get patient ID and claim numbers from EOB
[ ] Locate original bill/receipt from provider
[ ] Request written explanation from provider about billing
[ ] Contact insurance member services line
[ ] Get appeal process details and deadline

WEEK 2-3:
[ ] Request Explanation of Benefits (EOB) if missing
[ ] Obtain complete medical records from provider
[ ] Get itemized bill from provider (if not in EOB)
[ ] Get letter from physician supporting medical necessity
[ ] Organize all documents in chronological order
[ ] Make copies of everything

PREPARE WRITTEN APPEAL:
[ ] Use appeal letter template provided
[ ] Attach signed copies (originals kept by you)
[ ] Send via certified mail with return receipt
[ ] Keep copies of everything sent
[ ] Note deadline for appeal response (usually 30 days)

IF APPEAL DENIED:
[ ] Request external review (if available in your state)
[ ] Contact patient advocacy organization
[ ] Consult with medical billing advocate
[ ] Consider small claims court for smaller amounts

TRACKING:
Issue: {analysis.claims[0].claim_id if analysis.claims else 'N/A'}
Amount: ${analysis.total_patient_responsibility:,.2f}
Appeal Sent Date: ___________
Response Deadline: ___________
Appeal Status: ___________
"""
    return checklist


def _generate_talking_points(analysis: schemas.EOBAnalysis) -> str:
    """Generate negotiation talking points and arguments."""
    points = f"""
NEGOTIATION TALKING POINTS & ARGUMENTS

YOUR SITUATION:
- Total billed: ${analysis.total_billed:,.2f}
- Amount insurance covered: ${analysis.total_paid_by_insurance:,.2f}
- Amount you're being asked to pay: ${analysis.total_patient_responsibility:,.2f}
- Potential savings if successful: ${analysis.total_potential_savings:,.2f}

EFFECTIVE ARGUMENTS:

1. "This is medically necessary"
   * "My doctor prescribed/ordered this service based on my medical condition."
   * "Delaying or denying this would be harmful to my health."
   * "This is standard of care for my condition according to [medical guideline]."

2. "This should be covered"
   * "Similar services were covered when I used [other in-network provider]."
   * "The plan summary clearly lists [service type] as a covered benefit."
   * "I paid premiums in good faith based on plan coverage promises."

3. "This violates the No Surprises Act" (if applicable)
   * "I received emergency care at an in-network facility."
   * "I had no way to know the physician was out-of-network."
   * "Federal law protects me from surprise balance billing."

4. "This is a billing error"
   * "I was billed twice for the same service."
   * "The procedure codes don't match the service provided."
   * "The allowed amount is significantly below national standards."

5. "Significant financial hardship"
   * "This bill represents [X]% of my monthly income."
   * "Paying this would prevent me from paying other essential bills."
   * "I am eligible for financial assistance programs."

RESPONSES TO COMMON OBJECTIONS:

"It's not covered by your plan"
-> "Can you show me where in my plan documents it says this is excluded? 
   Because it clearly lists this service as covered."

"The provider is out-of-network"
-> "I received emergency care at an in-network facility. Federal law protects me. 
   Please apply in-network rates."

"That's what the provider charges"
-> "That's not my responsibility to pay if insurance says it's covered. 
   That's contractual between you and the provider."

"Insurance already paid"
-> "Insurance paid what they deemed appropriate. Any balance should be written off, 
   not billed to me."
"""
    return points

