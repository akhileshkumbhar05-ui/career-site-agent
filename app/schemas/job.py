from typing import Literal, Optional
from pydantic import BaseModel, Field


class JobLead(BaseModel):
    company: str
    title: str
    discovered_url: str
    source: str
    location: Optional[str] = None
    posted_date: Optional[str] = None


class OfficialJobResolutionRequest(BaseModel):
    company: str
    title: str
    discovered_url: str
    source: str


class OfficialJobResolutionResponse(BaseModel):
    canonical_job_id: str
    official_url: str
    ats_type: str
    status: str
    confidence: float = Field(ge=0.0, le=1.0)


class JDParseRequest(BaseModel):
    job_id: str
    title: str
    company: str
    official_url: Optional[str] = None
    jd_text: str


class ParsedJD(BaseModel):
    job_id: str
    company: str
    title: str
    required_skills: list[str]
    preferred_skills: list[str]
    years_required: Optional[str] = None
    education: Optional[str] = None
    responsibilities: list[str]
    keywords: list[str]
    constraints: list[str]
    # Raw JD text carried through from JDParseRequest so Claude tailoring
    # receives the full posting, not just extracted fields.
    jd_text: Optional[str] = None


class JobQualityGateRequest(BaseModel):
    company: str = ""
    title: str
    jd_text: str = ""
    location: Optional[str] = None
    source: str = "manual"


class JobQualityGateResponse(BaseModel):
    decision: Literal["pass", "review", "reject"]
    actionable: bool
    role_key: Optional[str] = None
    reasons: list[str] = []
    blockers: list[str] = []
    signals: list[str] = []
    title_score: int = 0
    keyword_score: int = 0
    years_required: Optional[float] = None
    experience_risk: Literal["low", "medium", "high"] = "low"
    authorization_risk: Literal["low", "medium", "high"] = "low"
