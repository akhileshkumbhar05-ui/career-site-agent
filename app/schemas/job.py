from typing import Optional
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
