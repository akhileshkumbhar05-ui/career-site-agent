from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.resume import TailoringPreferences
from app.schemas.tailoring_review import TailoringDraftResponse, TailoringReviewSelection


ApplicationLoopState = Literal[
    "imported",
    "fit_checked",
    "skipped",
    "draft_ready",
    "revision_requested",
    "approved_for_apply",
    "ats_opened",
    "submitted_confirmed",
    "sheet_logged",
    "recruiter_note_ready",
    "outreach_done",
]

ApplicationLoopActor = Literal["human", "agent", "system"]
ApplicationLoopMetricsWindow = Literal["today", "7d", "30d", "all"]
FitGateDecision = Literal["apply", "maybe", "skip"]
FitGateEvaluationStatus = Literal["complete", "needs_jd"]
ATSAssistStatus = Literal[
    "armed",
    "safe_fields_filled",
    "review_required",
    "technical_issue",
    "submitted_confirmed",
]
RecruiterOutreachStatus = Literal["ready", "sent"]


class ApplicationLoopCreateRequest(BaseModel):
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    job_url: str = ""
    source: str = "Unknown"
    lead_id: str = ""
    actor: ApplicationLoopActor = "human"


class ApplicationLoopTransitionRequest(BaseModel):
    target_state: ApplicationLoopState
    actor: ApplicationLoopActor = "human"
    note: str = Field(default="", max_length=1000)
    human_confirmed_submission: bool = False


class ApplicationLoopEvent(BaseModel):
    from_state: ApplicationLoopState | None = None
    to_state: ApplicationLoopState
    actor: ApplicationLoopActor
    note: str = ""
    occurred_at: str
    human_confirmed_submission: bool = False


class ApplicationLoopFitGateResult(BaseModel):
    decision: FitGateDecision
    evaluation_status: FitGateEvaluationStatus = "complete"
    score: int = Field(ge=0, le=100)
    one_line_reason: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    sponsorship_note: str = ""
    seniority_note: str = ""
    location_note: str = ""
    title_fit_note: str = ""
    skills_fit_note: str = ""
    deterministic_score: int = Field(default=0, ge=0, le=100)
    deterministic_decision: str = ""
    used_llm: bool = False
    cache_hit: bool = False
    scoring_mode: str = "deterministic_fallback"
    llm_provider: str = ""
    llm_model: str = ""
    evaluated_at: str
    overridden: bool = False
    original_decision: FitGateDecision | None = None
    override_note: str = ""


class ApplicationLoopTailoringDraftRef(BaseModel):
    draft_id: str
    version: int = Field(ge=1)
    base_score: int = Field(ge=0, le=100)
    tailored_score: int = Field(ge=0, le=100)
    revision_reason: str = ""
    preferences: TailoringPreferences | None = None
    preference_memory_fingerprint: str = ""
    preference_memory_role_family: str = ""
    preference_memory_source_count: int = Field(default=0, ge=0)
    engine: str = ""
    model: str = ""
    llm_usage: dict = Field(default_factory=dict)
    claude_call_consumed: bool = False
    created_at: str


class ApplicationLoopTailoringApproval(BaseModel):
    draft_id: str
    review: TailoringReviewSelection
    note: str
    approved_at: str


class ApplicationLoopExportHandoff(BaseModel):
    version: int = Field(ge=1)
    draft_id: str
    exported_at: str
    output_root_override: str = ""
    render_pdf_requested: bool = True
    quality_passed: bool
    quality_checks: list[dict] = Field(default_factory=list)
    docx_ready: bool
    pdf_ready: bool
    pdf_error: str = ""
    docx_download_path: str
    pdf_download_path: str = ""
    prepared_resume_docx_path: str
    prepared_resume_pdf_path: str = ""
    packet_folder_path: str = ""
    prepared_apply_plan_path: str = ""
    jd_path: str = ""
    cover_letter_path: str = ""
    files_written: list[str] = Field(default_factory=list)


class ApplicationLoopATSReviewItem(BaseModel):
    field_id: str = ""
    label: str = ""
    action: str = ""
    reason: str = ""
    sensitive: bool = False
    source: str = ""


class ApplicationLoopATSAssist(BaseModel):
    version: int = Field(ge=1)
    task_id: str
    status: ATSAssistStatus = "armed"
    target_url: str
    apply_plan_path: str
    preferred_resume_path: str
    preferred_resume_format: Literal["pdf", "docx"]
    opened_at: str
    expires_at: str
    last_result_at: str = ""
    filled_count: int = Field(default=0, ge=0)
    total_fields: int = Field(default=0, ge=0)
    fillable_count: int = Field(default=0, ge=0)
    manual_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)
    review_items: list[ApplicationLoopATSReviewItem] = Field(default_factory=list)
    quality_review_note: str = ""
    technical_issue_note: str = ""
    sheets_status_proposal: str = ""


class ApplicationLoopRecruiterOutreach(BaseModel):
    version: int = Field(ge=1)
    status: RecruiterOutreachStatus = "ready"
    recruiter_name: str = Field(default="", max_length=200)
    linkedin_search_url: str
    connection_note: str = Field(min_length=1, max_length=300)
    engine: str = "deterministic_fallback"
    model: str = ""
    cache_key: str = ""
    llm_usage: dict = Field(default_factory=dict)
    claude_call_consumed: bool = False
    generated_at: str
    edited_at: str = ""
    sent_at: str = ""
    sent_note: str = ""


class ApplicationLoopItem(BaseModel):
    loop_id: str
    company: str
    role: str
    job_url: str = ""
    source: str = "Unknown"
    jd_text: str = ""
    batch_id: str = ""
    canonical_job_url: str = ""
    state: ApplicationLoopState = "imported"
    revision_count: int = Field(default=0, ge=0)
    fit_gate: ApplicationLoopFitGateResult | None = None
    fit_gate_history: list[ApplicationLoopFitGateResult] = Field(default_factory=list)
    tailoring_draft: ApplicationLoopTailoringDraftRef | None = None
    tailoring_history: list[ApplicationLoopTailoringDraftRef] = Field(default_factory=list)
    tailoring_approval: ApplicationLoopTailoringApproval | None = None
    export_handoff: ApplicationLoopExportHandoff | None = None
    ats_assist: ApplicationLoopATSAssist | None = None
    recruiter_outreach: ApplicationLoopRecruiterOutreach | None = None
    created_at: str
    updated_at: str
    history: list[ApplicationLoopEvent] = Field(default_factory=list)


class ApplicationLoopMetricFunnelStage(BaseModel):
    state: ApplicationLoopState
    label: str
    count: int = Field(ge=0)
    percent_of_imported: float = Field(ge=0, le=100)
    kind: Literal["milestone", "exit"] = "milestone"


class ApplicationLoopMetricTiming(BaseModel):
    key: str
    label: str
    from_state: ApplicationLoopState
    to_state: ApplicationLoopState
    sample_count: int = Field(ge=0)
    average_minutes: float = Field(ge=0)
    median_minutes: float = Field(ge=0)


class ApplicationLoopMetricReason(BaseModel):
    reason: str
    count: int = Field(ge=1)


class ApplicationLoopMetricBottleneck(BaseModel):
    key: str = ""
    label: str
    average_minutes: float = Field(ge=0)
    sample_count: int = Field(ge=0)


class ApplicationLoopMetricsSummary(BaseModel):
    total_applications: int = Field(ge=0)
    fit_checked: int = Field(ge=0)
    skipped: int = Field(ge=0)
    draft_ready: int = Field(ge=0)
    approved: int = Field(ge=0)
    submitted: int = Field(ge=0)
    sheet_logged: int = Field(ge=0)
    recruiter_note_ready: int = Field(ge=0)
    outreach_done: int = Field(ge=0)
    portal_issues: int = Field(ge=0)
    total_revisions: int = Field(ge=0)
    average_revisions_per_tailored: float = Field(ge=0)
    average_tailoring_score_lift: float = Field(ge=0)
    average_minutes_to_submission: float = Field(ge=0)
    submission_rate: float = Field(ge=0, le=100)
    sheet_logging_rate: float = Field(ge=0, le=100)
    outreach_completion_rate: float = Field(ge=0, le=100)


class ApplicationLoopMetricsResponse(BaseModel):
    window: ApplicationLoopMetricsWindow
    window_label: str
    since: str = ""
    generated_at: str
    summary: ApplicationLoopMetricsSummary
    funnel: list[ApplicationLoopMetricFunnelStage]
    stage_timings: list[ApplicationLoopMetricTiming]
    bottleneck: ApplicationLoopMetricBottleneck
    skip_reasons: list[ApplicationLoopMetricReason]
    portal_failure_reasons: list[ApplicationLoopMetricReason]
    current_state_counts: dict[str, int] = Field(default_factory=dict)


class ApplicationLoopTailoringMemorySample(BaseModel):
    company: str
    role: str
    approved_at: str
    revision_count: int = Field(ge=0)


class ApplicationLoopTailoringMemoryResponse(BaseModel):
    role_family: str
    role_family_label: str
    available: bool = False
    approved_sample_count: int = Field(ge=0)
    correction_count: int = Field(ge=0)
    recommended_preferences: TailoringPreferences = Field(default_factory=TailoringPreferences)
    learned_instructions: list[str] = Field(default_factory=list)
    source_roles: list[str] = Field(default_factory=list)
    samples: list[ApplicationLoopTailoringMemorySample] = Field(default_factory=list)
    latest_approval_at: str = ""
    fingerprint: str = ""


BatchImportStatus = Literal["imported", "duplicate", "invalid"]


class ApplicationLoopBatchItemRequest(BaseModel):
    company: str = Field(default="", max_length=300)
    role: str = Field(default="", max_length=500)
    job_url: str = Field(default="", max_length=4000)
    jd_text: str = Field(default="", max_length=100_000)
    source: str = Field(default="Jobright AI", max_length=200)


class ApplicationLoopBatchImportRequest(BaseModel):
    items: list[ApplicationLoopBatchItemRequest] = Field(min_length=1, max_length=10)


class ApplicationLoopBatchOutcome(BaseModel):
    input_index: int = Field(ge=0)
    status: BatchImportStatus
    reason: str = ""
    loop_item: ApplicationLoopItem | None = None


class ApplicationLoopBatchSummary(BaseModel):
    requested: int = Field(ge=0)
    imported: int = Field(ge=0)
    duplicate: int = Field(ge=0)
    invalid: int = Field(ge=0)


class ApplicationLoopBatchResponse(BaseModel):
    batch_id: str
    created_at: str
    summary: ApplicationLoopBatchSummary
    outcomes: list[ApplicationLoopBatchOutcome]


class ApplicationLoopBatchItemReview(BaseModel):
    valid: bool
    reason: str = ""
    normalized_item: ApplicationLoopBatchItemRequest | None = None
    canonical_job_url: str = ""
    duplicate_reason: str = ""
    existing_loop_item: ApplicationLoopItem | None = None


ThirdEyeIntakeDestination = Literal["active_sprint", "inbox"]
ThirdEyeIntakeAction = Literal[
    "added_to_sprint",
    "added_to_inbox",
    "duplicate_in_sprint",
    "duplicate_inbox",
]


class ThirdEyeIntakeRequest(ApplicationLoopBatchItemRequest):
    destination: ThirdEyeIntakeDestination = "active_sprint"


class ThirdEyeSprintContext(BaseModel):
    sprint_id: str
    name: str
    status: Literal["active", "paused", "completed"]
    open_slots: int = Field(ge=0)
    target_count: int = Field(ge=1, le=10)
    active_job_count: int = Field(ge=0)
    accepts_items: bool


class ThirdEyeIntakeReviewResponse(BaseModel):
    valid: bool
    reason: str = ""
    normalized_item: ApplicationLoopBatchItemRequest | None = None
    canonical_job_url: str = ""
    duplicate_reason: str = ""
    existing_loop_item: ApplicationLoopItem | None = None
    already_in_current_sprint: bool = False
    sprint: ThirdEyeSprintContext | None = None
    recommended_destination: ThirdEyeIntakeDestination = "inbox"
    claude_calls: int = 0


class ThirdEyeIntakeResponse(BaseModel):
    action: ThirdEyeIntakeAction
    message: str
    import_status: BatchImportStatus
    duplicate_reason: str = ""
    loop_item: ApplicationLoopItem
    sprint: ThirdEyeSprintContext | None = None
    claude_calls: int = 0


class ApplicationLoopFitGateRunRequest(BaseModel):
    loop_ids: list[str] = Field(min_length=1, max_length=10)
    use_llm: bool = True
    force_refresh: bool = False


FitGateOutcomeStatus = Literal["evaluated", "cached", "needs_jd", "error"]


class ApplicationLoopFitGateOutcome(BaseModel):
    loop_id: str
    status: FitGateOutcomeStatus
    result: ApplicationLoopFitGateResult | None = None
    loop_item: ApplicationLoopItem | None = None
    error: str = ""


class ApplicationLoopFitGateSummary(BaseModel):
    requested: int = Field(ge=0)
    evaluated: int = Field(ge=0)
    cached: int = Field(ge=0)
    needs_jd: int = Field(ge=0)
    apply: int = Field(ge=0)
    maybe: int = Field(ge=0)
    skip: int = Field(ge=0)
    llm_calls: int = Field(ge=0)
    failed: int = Field(ge=0)


class ApplicationLoopFitGateResponse(BaseModel):
    summary: ApplicationLoopFitGateSummary
    outcomes: list[ApplicationLoopFitGateOutcome]


class ApplicationLoopFitOverrideRequest(BaseModel):
    decision: FitGateDecision
    note: str = Field(min_length=3, max_length=1000)


class ApplicationLoopJDUpdateRequest(BaseModel):
    jd_text: str = Field(min_length=20, max_length=100_000)


class ApplicationLoopSheetLoggedRequest(BaseModel):
    note: str = Field(min_length=3, max_length=1000)
    sheet_write_succeeded: bool = False


class ApplicationLoopTailoringDraftRequest(BaseModel):
    preferences: TailoringPreferences = Field(default_factory=TailoringPreferences)
    revision_reason: str = Field(default="", max_length=1000)
    preference_memory_fingerprint: str = Field(default="", max_length=64)


class ApplicationLoopTailoringDraftResponse(BaseModel):
    loop_item: ApplicationLoopItem
    draft: TailoringDraftResponse


class ApplicationLoopTailoringApproveRequest(TailoringReviewSelection):
    approval_note: str = Field(min_length=3, max_length=1000)


class ApplicationLoopTailoringApproveResponse(BaseModel):
    loop_item: ApplicationLoopItem
    draft_id: str
    resume_preview_html: str
    message: str


class ApplicationLoopTailoringExportRequest(BaseModel):
    output_root_override: str = Field(default="", max_length=4000)
    render_pdf: bool = True
    human_confirmed_export: bool = False


class ApplicationLoopTailoringExportResponse(BaseModel):
    loop_item: ApplicationLoopItem
    handoff: ApplicationLoopExportHandoff
    message: str


class ApplicationLoopATSArmRequest(BaseModel):
    expires_minutes: int = Field(default=30, ge=1, le=240)
    quality_review_note: str = Field(default="", max_length=1000)


class ApplicationLoopATSAssistResponse(BaseModel):
    loop_item: ApplicationLoopItem
    assist: ApplicationLoopATSAssist
    message: str


class ApplicationLoopATSOutcomeRequest(BaseModel):
    outcome: Literal["technical_issue", "submitted_confirmed"]
    note: str = Field(min_length=3, max_length=1000)
    human_confirmed_submission: bool = False


class ApplicationLoopATSOutcomeResponse(BaseModel):
    loop_item: ApplicationLoopItem
    assist: ApplicationLoopATSAssist
    sheet_row_proposal: dict[str, str]
    message: str


class ApplicationLoopOutreachBatchRequest(BaseModel):
    loop_ids: list[str] = Field(min_length=1, max_length=10)
    use_llm: bool = True
    force_refresh: bool = False


OutreachBatchOutcomeStatus = Literal["ready", "cached", "error"]


class ApplicationLoopOutreachBatchOutcome(BaseModel):
    loop_id: str
    company: str = ""
    role: str = ""
    status: OutreachBatchOutcomeStatus
    outreach: ApplicationLoopRecruiterOutreach | None = None
    loop_item: ApplicationLoopItem | None = None
    error: str = ""


class ApplicationLoopOutreachCompanyGroup(BaseModel):
    company: str
    outcomes: list[ApplicationLoopOutreachBatchOutcome]


class ApplicationLoopOutreachBatchSummary(BaseModel):
    requested: int = Field(ge=0)
    companies: int = Field(ge=0)
    ready: int = Field(ge=0)
    cached: int = Field(ge=0)
    llm_calls: int = Field(ge=0)
    failed: int = Field(ge=0)


class ApplicationLoopOutreachBatchResponse(BaseModel):
    generated_at: str
    summary: ApplicationLoopOutreachBatchSummary
    groups: list[ApplicationLoopOutreachCompanyGroup]
    outcomes: list[ApplicationLoopOutreachBatchOutcome]


class ApplicationLoopOutreachUpdateRequest(BaseModel):
    recruiter_name: str = Field(default="", max_length=200)
    connection_note: str = Field(min_length=20, max_length=300)


class ApplicationLoopOutreachSentRequest(BaseModel):
    note: str = Field(min_length=3, max_length=1000)
    human_confirmed_sent: bool = False


class ApplicationLoopOutreachResponse(BaseModel):
    loop_item: ApplicationLoopItem
    outreach: ApplicationLoopRecruiterOutreach
    message: str
