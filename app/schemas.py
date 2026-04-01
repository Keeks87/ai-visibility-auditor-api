from pydantic import BaseModel, HttpUrl, EmailStr


class AuditRequest(BaseModel):
    url: HttpUrl


class LeadRequest(BaseModel):
    email: EmailStr
    url: HttpUrl
    name: str | None = None
    company: str | None = None
