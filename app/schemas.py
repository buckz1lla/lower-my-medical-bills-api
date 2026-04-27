from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date

# ===== EOB LINE ITEM SCHEMAS =====

class LineItem(BaseModel):
    """Individual claim line item from EOB"""
    service_date: Optional[date] = None
    provider_name: str
    service_description: str
    billed_amount: float
    allowed_amount: float
    patient_responsibility: float
    insurance_paid: float
    status: str  # "paid", "denied", "pending", "partial"
    reason_code: Optional[str] = None
    notes: Optional[str] = None

class ClaimGroup(BaseModel):
    """Group of related claims (e.g., same visit)"""
    claim_id: str
    visit_date: date
    provider_name: str
    provider_npi: Optional[str] = None
    facility_name: Optional[str] = None
    line_items: List[LineItem]
    in_network: Optional[bool] = None
    network_status: str = "unknown"  # "in_network", "out_of_network", "unknown"
    network_confidence: str = "low"  # "high", "medium", "low"
    evidence: List[str] = Field(default_factory=list)
    missing_data_points: List[str] = Field(default_factory=list)
    # Backward-compatible fields kept for existing clients.
    network_evidence: List[str] = Field(default_factory=list)
    network_missing_data_points: List[str] = Field(default_factory=list)
    total_billed: float
    total_allowed: float
    total_paid_by_insurance: float
    total_patient_responsibility: float

# ===== SAVINGS OPPORTUNITY SCHEMAS =====

class SavingsOpportunity(BaseModel):
    """Identified opportunity to save money"""
    opportunity_id: str
    type: str  # "billing_error", "out_of_network", "wrong_plan", "appeal", "alternative"
    claim_id: str
    severity: str  # "critical", "high", "medium", "low"
    estimated_savings: float
    description: str
    recommended_action: str
    difficulty_level: str  # "easy", "medium", "hard"
    time_estimate_days: int
    confidence_score: float  # 0-1 confidence this is actionable
    confidence_level: str  # "high", "medium", "low"
    evidence: List[str] = Field(default_factory=list)
    flag_reason: str
    verification_steps: List[str]
    could_be_correct_if: List[str]
    missing_data_points: List[str]
    appeal_deadline: Optional[date] = None  # 180 days from visit date; None when date unavailable
    appeal_deadline_note: Optional[str] = None  # Human-readable urgency message

class AppealRecommendation(BaseModel):
    """Recommendation for appealing a claim"""
    claim_id: str
    reason: str
    success_probability: float  # 0-1
    steps: List[str]
    contact_info: Optional[dict] = None  # phone, email, address

# ===== EOB ANALYSIS SCHEMAS =====

class EOBAnalysis(BaseModel):
    """Complete analysis of an EOB"""
    analysis_id: str
    file_name: str
    upload_date: Optional[date] = None
    analysis_date: date
    claims: List[ClaimGroup]
    total_billed: float
    total_paid_by_insurance: float
    total_patient_responsibility: float
    total_potential_savings: float
    savings_opportunities: List[SavingsOpportunity]
    appeal_recommendations: List[AppealRecommendation]
    key_metrics: dict  # Summary metrics

class EOBUploadResponse(BaseModel):
    """Response after uploading an EOB file"""
    message: str
    analysis_id: str
    file_name: str
    status: str  # "processing", "completed", "error"

# ===== USER CONTEXT SCHEMAS =====

class UserProfile(BaseModel):
    """User information for personalized analysis"""
    plan_type: Optional[str] = None  # "HMO", "PPO", "HDHP", "POS"
    annual_deductible: Optional[float] = None
    deductible_met: Optional[float] = None
    out_of_pocket_max: Optional[float] = None
    out_of_pocket_spent: Optional[float] = None
    insurance_provider: Optional[str] = None
    is_in_network_preferred: Optional[bool] = True
