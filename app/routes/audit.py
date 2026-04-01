from fastapi import APIRouter, HTTPException

from app.schemas import AuditRequest
from app.services.auditor import audit_url

router = APIRouter()


@router.post("/audit")
def run_audit(payload: AuditRequest):
    try:
        result = audit_url(str(payload.url))
        flat = result["flat"]

        return {
            "ok": True,
            "fetch_confidence": flat.get("fetch_confidence", "Unknown"),
            "overall_score": flat.get("overall_ai_visibility_score"),
            "score_band": flat.get("score_band", "Unknown"),
            "summary": result.get("audit_summary", ""),
            "teaser_recommendations": [
                rec["message"] for rec in result.get("recommendations", [])[:2]
            ],
            "full_report_locked": True,
            "audit_data": {
                "final_url": flat.get("final_url"),
                "status_code": flat.get("status_code"),
                "title": flat.get("title"),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {e}")
