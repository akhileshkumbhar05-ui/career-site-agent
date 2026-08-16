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
FitGateDecision = Literal["apply", "maybe", "skip"]
FitGateEvaluationStatus = Literal["complete", "needs_jd"]


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
    created_at: str
    updated_at: str
    history: list[ApplicationLoopEvent] = Field(default_factory=list)


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


class ApplicationLoopTailoringDraftRequest(BaseModel):
    preferences: TailoringPreferences = Field(default_factory=TailoringPreferences)
    revision_reason: str = Field(default="", max_length=1000)


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
