from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
import uuid
from datetime import date, datetime
from app import schemas
from app.services import eob_analyzer
from app.store import eob_analyses, initialize_analysis_payment, payment_status_by_analysis

router = APIRouter()

@router.post("/upload", response_model=schemas.EOBUploadResponse)
async def upload_eob(
    file: UploadFile = File(...),
    user_profile: str = Query(None)  # JSON string of UserProfile
):
    """
    Upload an EOB file for analysis.
    
    Accepts PDF, image, or CSV formats.
    Returns analysis ID for querying results.
    """
    try:
        # Validate file type
        allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.csv', '.xlsx']
        file_ext = '.' + file.filename.split('.')[-1].lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"File type not supported. Allowed: {', '.join(allowed_extensions)}"
            )
        
        # Read file content
        content = await file.read()
        
        # Generate analysis ID
        analysis_id = str(uuid.uuid4())
        
        # Process file (in production, this would be async job)
        analysis = await eob_analyzer.analyze_eob(
            file_name=file.filename,
            content=content,
            file_type=file_ext,
            analysis_id=analysis_id
        )
        
        # Store analysis
        eob_analyses[analysis_id] = analysis
        initialize_analysis_payment(analysis_id)
        
        return schemas.EOBUploadResponse(
            message="EOB file uploaded and analysis started",
            analysis_id=analysis_id,
            file_name=file.filename,
            status="completed"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analysis/{analysis_id}", response_model=schemas.EOBAnalysis)
async def get_analysis(analysis_id: str):
    """
    Retrieve analysis results for a previously uploaded EOB.
    """
    if analysis_id not in eob_analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    return eob_analyses[analysis_id]

@router.get("/savings-summary/{analysis_id}")
async def get_savings_summary(analysis_id: str):
    """
    Get a summary of savings opportunities for an EOB analysis.
    """
    if analysis_id not in eob_analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    analysis = eob_analyses[analysis_id]
    
    return {
        "analysis_id": analysis_id,
        "total_potential_savings": analysis.total_potential_savings,
        "opportunities_count": len(analysis.savings_opportunities),
        "critical_issues": [
            opp for opp in analysis.savings_opportunities 
            if opp.severity == "critical"
        ],
        "appeals_recommended": len(analysis.appeal_recommendations),
        "top_opportunity": (
            max(analysis.savings_opportunities, 
                key=lambda x: x.estimated_savings, default=None)
        ),
    }

@router.get("/opportunity-details/{analysis_id}/{opportunity_id}")
async def get_opportunity_details(analysis_id: str, opportunity_id: str):
    """
    Get detailed information about a specific savings opportunity.
    """
    if analysis_id not in eob_analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    analysis = eob_analyses[analysis_id]
    
    for opp in analysis.savings_opportunities:
        if opp.opportunity_id == opportunity_id:
            return {
                "opportunity": opp,
                "related_claim": next(
                    (claim for claim in analysis.claims 
                     if claim.claim_id == opp.claim_id), 
                    None
                )
            }
    
    raise HTTPException(status_code=404, detail="Opportunity not found")

@router.post("/compare")
async def compare_eobs(analysis_ids: list[str]):
    """
    Compare multiple EOB analyses to identify trends.
    """
    results = []
    total_savings_potential = 0
    
    for analysis_id in analysis_ids:
        if analysis_id not in eob_analyses:
            continue
        analysis = eob_analyses[analysis_id]
        results.append({
            "analysis_id": analysis_id,
            "file_name": analysis.file_name,
            "date": analysis.analysis_date,
            "total_savings": analysis.total_potential_savings,
            "opportunity_count": len(analysis.savings_opportunities)
        })
        total_savings_potential += analysis.total_potential_savings
    
    return {
        "analyses": results,
        "total_potential_savings": total_savings_potential,
        "average_per_eob": total_savings_potential / len(results) if results else 0
    }

@router.get("/templates/{analysis_id}")
async def get_appeal_templates(analysis_id: str):
    """
    Generate personalized appeal templates and scripts for an EOB analysis.
    
    Includes:
    - Formal appeal letter
    - Phone script for insurer
    - Phone script for provider
    - Appeal checklist
    - Negotiation talking points
    """
    if analysis_id not in eob_analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")

    payment_record = payment_status_by_analysis.get(analysis_id, {})
    if payment_record.get("status") != "paid":
        raise HTTPException(status_code=403, detail="Payment required before accessing templates")
    
    analysis = eob_analyses[analysis_id]
    
    # Generate templates
    templates = eob_analyzer.generate_appeal_templates(analysis)
    
    return {
        "analysis_id": analysis_id,
        "templates": templates,
        "generated_at": datetime.now().isoformat(),
        "instructions": {
            "appeal_letter": "Use this formal letter to file a written appeal with your insurance company. Send via certified mail.",
            "phone_script_insurer": "Use this script when calling your insurance company's appeals department.",
            "phone_script_provider": "Use this script when negotiating with the provider or facility billing department.",
            "appeal_checklist": "Follow these steps in order to maximize your chances of a successful appeal.",
            "negotiation_talking_points": "Reference these points if you're negotiating directly with the provider about costs."
        }
    }

