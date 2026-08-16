from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
