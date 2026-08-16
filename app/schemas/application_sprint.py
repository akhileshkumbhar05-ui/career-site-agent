from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.application_loop import ApplicationLoopItem


ApplicationSprintStatus = Literal["active", "paused", "completed"]
ApplicationSprintActionKey = Literal[
    "add_jd",
    "run_fit_gate",
    "review_fit",
    "tailor_resume",
    "wait_for_draft",
    "review_resume",
    "export_resume",
    "open_ats",
    "resolve_portal_issue",
    "confirm_submission",
    "log_sheets",
    "ready_for_outreach",
    "review_outreach",
    "done",
    "replace_job",
]


class ApplicationSprintCreateRequest(BaseModel):
    name: str = Field(default="10-Job Sprint", min_length=1, max_length=120)
    target_count: int = Field(default=10, ge=1, le=10)
    loop_ids: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_capacity(self):
        if len(set(self.loop_ids)) != len(self.loop_ids):
            raise ValueError("Sprint jobs must be unique.")
        if len(self.loop_ids) > self.target_count:
            raise ValueError("Initial jobs cannot exceed the sprint target.")
        return self


class ApplicationSprintAddItemsRequest(BaseModel):
    loop_ids: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_unique_jobs(self):
        if len(set(self.loop_ids)) != len(self.loop_ids):
            raise ValueError("Replacement jobs must be unique.")
        return self


class ApplicationSprintNextAction(BaseModel):
    key: ApplicationSprintActionKey
    label: str
    detail: str
    manual_gate: bool = False


class ApplicationSprintItem(BaseModel):
    position: int = Field(ge=1)
    added_at: str
    counted_toward_target: bool
    is_current: bool = False
    next_action: ApplicationSprintNextAction
    loop_item: ApplicationLoopItem


class ApplicationSprintStats(BaseModel):
    target_count: int = Field(ge=1, le=10)
    active_job_count: int = Field(ge=0)
    history_count: int = Field(ge=0)
    submitted_count: int = Field(ge=0)
    sheet_logged_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    open_slots: int = Field(ge=0)
    revision_count: int = Field(ge=0)
    claude_calls: int = Field(ge=0)
    elapsed_seconds: int = Field(ge=0)


class ApplicationSprintResponse(BaseModel):
    sprint_id: str
    name: str
    status: ApplicationSprintStatus
    started_at: str
    paused_at: str = ""
    completed_at: str = ""
    updated_at: str
    current_loop_id: str = ""
    outreach_unlocked: bool = False
    ready_for_next_sprint: bool = False
    outreach_loop_ids: list[str] = Field(default_factory=list)
    stats: ApplicationSprintStats
    items: list[ApplicationSprintItem]
