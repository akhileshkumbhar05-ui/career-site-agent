from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.ats_autofill import AutofillContextRequest
from app.schemas.resume import TailoringBulletCounts, TailoringPreferences


class TailoringDraftRequest(AutofillContextRequest):
    force_prepare: bool = True
    tailoring_preferences: TailoringPreferences = Field(default_factory=TailoringPreferences)


class TailoringDraftBullet(BaseModel):
    bullet_id: str
    section: str
    item_id: str = ""
    item_label: str = ""
    original: str
    proposed: str


class TailoringDraftProject(BaseModel):
    project_id: str
    name: str
    selected: bool = True


class TailoringDraftPublication(BaseModel):
    publication_id: str
    title: str
    venue: str = ""
    year: str = ""
    selected: bool = True


class TailoringDraftResponse(BaseModel):
    draft_id: str
    company: str
    role: str
    target_role_key: str = ""
    base_score: int
    tailored_score: int
    preferences: TailoringPreferences
    summary_original: str
    summary_proposed: str
    bullets: list[TailoringDraftBullet] = Field(default_factory=list)
    projects: list[TailoringDraftProject] = Field(default_factory=list)
    publications: list[TailoringDraftPublication] = Field(default_factory=list)
    skill_gaps: list[str] = Field(default_factory=list)
    connection_note: str = ""
    cover_letter_text: str = ""
    changes_summary: list[str] = Field(default_factory=list)
    resume_preview_html: str = ""
    message: str
    engine: str = ""
    model: str = ""
    llm_usage: dict = Field(default_factory=dict)
    claude_call_consumed: bool = False


class TailoringBulletDecision(BaseModel):
    bullet_id: str
    accepted: bool = True
    text: str = Field(default="", max_length=700)


class TailoringReviewSelection(BaseModel):
    draft_id: str
    summary_accepted: bool = True
    summary_text: str = Field(default="", max_length=1400)
    bullets: list[TailoringBulletDecision] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list, max_length=3)
    publication_ids: list[str] = Field(default_factory=list, max_length=2)
    bullet_counts: TailoringBulletCounts = Field(default_factory=TailoringBulletCounts)
    connection_note: str = Field(default="", max_length=299)
    cover_letter_accepted: bool = True
    cover_letter_text: str = Field(default="", max_length=4000)


class TailoringFinalizeRequest(TailoringReviewSelection):
    output_root_override: str = ""
    render_pdf: bool = True


class TailoringFinalizeResponse(BaseModel):
    draft_id: str
    quality_passed: bool
    quality_checks: list[dict] = Field(default_factory=list)
    docx_ready: bool
    pdf_ready: bool
    docx_download_path: str
    pdf_download_path: str = ""
    prepared_resume_docx_path: str
    prepared_resume_pdf_path: str = ""
    prepared_apply_plan_path: str = ""
    packet_folder_path: str = ""
    jd_path: str = ""
    apply_url: str = ""
    cover_letter_path: str = ""
    files_written: list[str] = Field(default_factory=list)
    pdf_error: str = ""
    message: str


class TailoringPreviewRenderResponse(BaseModel):
    draft_id: str
    resume_preview_html: str
    message: str = "Preview rendered locally."
