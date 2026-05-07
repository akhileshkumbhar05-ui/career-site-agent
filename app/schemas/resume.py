from typing import Optional
from pydantic import BaseModel

from app.schemas.job import ParsedJD


class ResumeScoreRequest(BaseModel):
    job_id: str
    resume_version: str = "base_resume_v1"
    parsed_jd: ParsedJD


class ResumeScoreResponse(BaseModel):
    job_id: str
    resume_version: str
    overall_score: int
    required_skills_score: int
    preferred_skills_score: int
    experience_score: int
    education_score: int
    domain_score: int
    constraints_score: int
    missing_items: list[str]
    matched_skills: list[str]
    recommendation: str


class ResumeTailorRequest(BaseModel):
    job_id: str
    resume_version: str = "base_resume_v1"
    parsed_jd: ParsedJD
    current_score: int


class ResumeTailorResponse(BaseModel):
    job_id: str
    source_resume_version: str
    tailored_resume_version: str
    changes_summary: list[str]
    tailored_score: int
    selected_project_ids: list[str]


class ResumeDecisionRequest(BaseModel):
    job_id: str
    base_score: int
    tailored_score: Optional[int] = None


class ResumeDecisionResponse(BaseModel):
    job_id: str
    decision: str
    reason: str
