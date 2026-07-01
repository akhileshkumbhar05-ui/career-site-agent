from fastapi import APIRouter
from pydantic import BaseModel

from app.services.email_classifier import classify_email

router = APIRouter()


class EmailClassifyRequest(BaseModel):
    subject: str
    body: str
    sender_email: str = ""
    sender_name: str = ""


class EmailClassifyResponse(BaseModel):
    company_name: str
    email_type: str
    new_status: str
    confidence: float
    reasoning: str
    requires_review: bool
    is_job_related: bool
    matched_rule: str
    matched_pattern: str


@router.post("/classify", response_model=EmailClassifyResponse)
def classify(payload: EmailClassifyRequest) -> EmailClassifyResponse:
    """Classify job-application email updates for the n8n Gmail workflow."""
    result = classify_email(
        subject=payload.subject,
        body=payload.body,
        sender_email=payload.sender_email,
        sender_name=payload.sender_name,
    )
    return EmailClassifyResponse(**result)
