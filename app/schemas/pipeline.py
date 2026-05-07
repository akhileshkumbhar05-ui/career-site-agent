from typing import Optional, Literal
from pydantic import BaseModel


class JobProcessRequest(BaseModel):
    job_id: str
    company: str
    title: str
    jd_text: str
    discovered_url: str = ""
    source: str = "manual"
    posted_at: Optional[str] = None


class JobProcessResponse(BaseModel):
    job_id: str
    company: str
    title: str
    canonical_job_id: str
    official_url: str
    ats_type: str
    resolution_status: str
    resolution_confidence: float
    base_score: int
    tailored_score: Optional[int] = None
    decision: Literal["apply_now", "manual_review", "reject"]
    decision_reason: str
    recommended_resume_version: str
    tracker_status: Literal["Applied", "Rejection", "Not Applied"]