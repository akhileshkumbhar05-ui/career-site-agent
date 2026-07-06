from typing import Literal, Optional
from pydantic import BaseModel, Field

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


class TailoringBulletCounts(BaseModel):
    experience_per_role: int = Field(default=3, ge=0, le=50)
    projects_per_project: int = Field(default=2, ge=0, le=50)
    research_per_paper: int = Field(default=2, ge=0, le=50)


class TailoringPreferences(BaseModel):
    preset: Literal[
        "balanced",
        "technical_depth",
        "business_impact",
        "projects_first",
        "experience_first",
        "minimal_edits",
    ] = "balanced"
    rewrite_intensity: Literal["light", "balanced", "strong"] = "balanced"
    emphasis: list[Literal["summary", "experience", "projects", "skills", "research_papers"]] = Field(
        default_factory=lambda: ["summary", "experience", "projects", "skills"],
        max_length=5,
    )
    custom_instructions: str = Field(default="", max_length=600)
    include_connection_note: bool = True
    include_cover_letter: bool = False
    bullet_counts: TailoringBulletCounts = Field(default_factory=TailoringBulletCounts)


class ResumeTailorRequest(BaseModel):
    job_id: str
    resume_version: str = "base_resume_v1"
    parsed_jd: ParsedJD
    current_score: int
    preferences: TailoringPreferences = Field(default_factory=TailoringPreferences)


class ResumeTailorResponse(BaseModel):
    job_id: str
    # Both old names kept so existing rule-based TailoringService doesn't break.
    # ClaudeTailoringService populates resume_version; old service populates both legacy fields.
    resume_version: str = ""
    source_resume_version: str = ""
    tailored_resume_version: str = ""

    tailored_score: int
    selected_project_ids: list[str] = []
    changes_summary: list[str] = []

    # New fields — only populated by ClaudeTailoringService
    # Optional so the rule-based fallback never has to set them
    summary_variant_key: Optional[str] = None
    summary_text: Optional[str] = None
    rewritten_bullets: Optional[list[dict]] = None   # [{"original": ..., "rewritten": ..., "project_id": ...}]
    skill_gaps: list[str] = []
    connection_note: Optional[str] = None            # LinkedIn connection note ≤ 299 chars
    cover_letter_text: Optional[str] = None


class ResumeDecisionRequest(BaseModel):
    job_id: str
    base_score: int
    tailored_score: Optional[int] = None


class ResumeDecisionResponse(BaseModel):
    job_id: str
    decision: str
    reason: str
