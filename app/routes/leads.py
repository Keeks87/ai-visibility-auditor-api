from fastapi import APIRouter

from app.schemas import LeadRequest

router = APIRouter()


@router.post("/lead")
def capture_lead(payload: LeadRequest):
    # MVP placeholder.
    # Later you can save this to a database, Google Sheet, CRM, etc.
    return {
        "ok": True,
        "message": "Lead captured successfully.",
        "lead": {
            "email": payload.email,
            "url": str(payload.url),
            "name": payload.name,
            "company": payload.company,
        },
    }
