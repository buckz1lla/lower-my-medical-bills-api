from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.services.fair_price_service import check_fair_price, search_procedures

router = APIRouter()


@router.get("/fair-price/check")
def fair_price_check(
    billed_amount: float = Query(..., gt=0, description="Amount billed on the statement"),
    cpt_code: Optional[str] = Query(None, description="CPT procedure code (e.g. 99213)"),
    procedure_query: Optional[str] = Query(None, description="Procedure name to search (e.g. 'office visit')"),
):
    """
    Compare a billed amount against the CMS Medicare benchmark rate.
    Provide either cpt_code or procedure_query.
    """
    if not cpt_code and not procedure_query:
        raise HTTPException(status_code=400, detail="Provide either cpt_code or procedure_query.")
    try:
        result = check_fair_price(
            billed_amount=billed_amount,
            cpt_code=cpt_code or None,
            procedure_query=procedure_query or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


@router.get("/fair-price/search")
def fair_price_search(
    q: str = Query(..., min_length=2, description="Procedure name search query"),
):
    """Return up to 8 procedure suggestions matching the query."""
    results = search_procedures(q, limit=8)
    return {"results": [{"cpt": r["cpt"], "description": r["description"], "category": r["category"]} for r in results]}
