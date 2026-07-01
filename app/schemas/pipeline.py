from typing import Optional, Literal
from pydantic import BaseModel

from app.schemas.application_packet import ApplicationPacket


class JobProcessRequest(BaseModel):
    job_id: str
    company: str
    title: str
    jd_text: str
    discovered_url: str = ""
    source: str = "manual"
    posted_at: Optional[str] = None
    location: Optional[str] = None


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
    quality_gate_decision: Optional[Literal["pass", "review", "reject"]] = None
    quality_gate_reasons: list[str] = []
    quality_gate_blockers: list[str] = []
    target_role_key: Optional[str] = None
    selected_project_ids: list[str] = []
    changes_summary: list[str] = []
    summary_text: Optional[str] = None
    rewritten_bullets: list[dict] = []
    connection_note: Optional[str] = None
    application_packet: Optional[ApplicationPacket] = None
