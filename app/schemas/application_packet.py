from pydantic import BaseModel, Field

from app.schemas.resume import TailoringBulletCounts


class ApplicationPacket(BaseModel):
    job_id: str = ""
    company: str
    role: str
    role_slug: str
    company_folder_path: str
    tailored_resume_path: str
    base_resume_pdf: str
    official_url: str
    target_role_key: str | None = None
    base_score: int
    tailored_score: int | None = None
    decision: str
    decision_reason: str
    prefill_profile: dict
    human_control_note: str
    source: str = ""
    posted_at: str | None = None
    location: str | None = None
    ats_answer_bank: dict = Field(default_factory=dict)
    recruiter_searches: list[dict] = Field(default_factory=list)
    application_steps: list[dict] = Field(default_factory=list)


class ApplicationPacketExportRequest(BaseModel):
    application_packet: ApplicationPacket
    output_root_override: str | None = None
    selected_project_ids: list[str] = []
    # Automated paths (queue worker, agents pipeline) leave selected_project_ids empty and
    # expect a top-3 fallback; the human review flow sets this False so deselect-all is honored.
    auto_select_projects: bool = True
    selected_publication_ids: list[str] = []
    include_publications: bool = False
    bullet_counts: TailoringBulletCounts = Field(default_factory=TailoringBulletCounts)
    changes_summary: list[str] = []
    summary_text: str | None = None
    rewritten_bullets: list[dict] = []
    jd_text: str = ""
    recruiter_subject: str = ""
    recruiter_body: str = ""
    connection_note: str = ""
    cover_letter_text: str = ""
    render_pdf: bool = False


class ApplicationPacketExportResponse(BaseModel):
    company_folder_path: str
    packet_folder_path: str
    tailored_resume_docx_path: str = ""
    tailored_resume_html_path: str
    intended_tailored_resume_pdf_path: str
    tailored_resume_pdf_path: str | None = None
    pdf_rendered: bool = False
    pdf_error: str = ""
    quality_passed: bool = False
    quality_checks: list[dict] = []
    metadata_path: str
    checklist_path: str
    outreach_path: str
    jd_path: str
    cover_letter_path: str = ""
    apply_plan_path: str = ""
    ats_answers_path: str = ""
    files_written: list[str]
