from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.audit import router as audit_router
from app.routes.leads import router as leads_router

app = FastAPI(title="AI Visibility Auditor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://keenanduplessis.com",
        "https://www.keenanduplessis.com",
        "http://localhost:3000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(audit_router, prefix="/api", tags=["audit"])
app.include_router(leads_router, prefix="/api", tags=["leads"])


@app.get("/")
def root():
    return {
        "ok": True,
        "message": "AI Visibility Auditor API is running."
    }
