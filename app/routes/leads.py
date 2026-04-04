import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import APIRouter, HTTPException

from app.schemas import LeadRequest

router = APIRouter()


def send_email_notification(payload: LeadRequest):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    notify_to = os.getenv("LEAD_NOTIFY_EMAIL")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass, notify_to]):
        raise ValueError("Missing SMTP environment variables.")

    subject = "New AI Visibility Audit Lead"

    body = f"""
New lead captured from the AI Visibility Audit tool.

Name: {payload.name or 'Not provided'}
Email: {payload.email}
Company: {payload.company or 'Not provided'}
URL Audited: {payload.url}
""".strip()

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = notify_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, notify_to, msg.as_string())


@router.post("/lead")
def capture_lead(payload: LeadRequest):
    try:
        send_email_notification(payload)
        return {
            "ok": True,
            "message": "Lead captured successfully."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lead email failed: {e}")
