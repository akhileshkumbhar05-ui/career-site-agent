from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.application_loop import ApplicationLoopItem
from app.schemas.sheets import AppliedUsingValue
from app.schemas.tracker import SheetsLogResponse


ThirdEyeCloseoutOutcome = Literal["submitted_confirmed", "technical_issue"]
ThirdEyeCloseoutMatchSource = Literal["explicit_loop", "autofill_task", "current_sprint", "single_open_ats"]


class ThirdEyeCloseoutReviewRequest(BaseModel):
    loop_id: str = Field(default="", max_length=100)
    task_id: str = Field(default="", max_length=100)
    url: str = Field(default="", max_length=4000)
    page_title: str = Field(default="", max_length=1000)
    page_text: str = Field(default="", max_length=40_000)


class ThirdEyeCloseoutReviewResponse(BaseModel):
    matched: bool
    reason: str = ""
    match_source: ThirdEyeCloseoutMatchSource | None = None
    loop_item: ApplicationLoopItem | None = None
    submitted_sheet_row: dict[str, str] = Field(default_factory=dict)
    technical_issue_sheet_row: dict[str, str] = Field(default_factory=dict)
    sheets_configured: bool = False
    already_recorded: bool = False
    claude_calls: int = 0


class ThirdEyeCloseoutRequest(BaseModel):
    loop_id: str = Field(min_length=1, max_length=100)
    outcome: ThirdEyeCloseoutOutcome
    note: str = Field(min_length=3, max_length=1000)
    human_confirmed_submission: bool = False
    log_to_sheets: bool = True
    salary_quoted: str = Field(default="N/A", max_length=300)
    source: str = Field(default="", max_length=200)
    applied_using: AppliedUsingValue | None = None


class ThirdEyeCloseoutProgress(BaseModel):
    sprint_id: str
    sprint_name: str
    sprint_status: Literal["active", "paused", "completed"]
    target_count: int = Field(ge=1, le=10)
    submitted_count: int = Field(ge=0)
    sheet_logged_count: int = Field(ge=0)
    current_loop_id: str = ""
    next_company: str = ""
    next_role: str = ""
    next_action: str = ""
    outreach_unlocked: bool = False


class ThirdEyeCloseoutResponse(BaseModel):
    outcome: ThirdEyeCloseoutOutcome
    loop_item: ApplicationLoopItem
    sheet_row: dict[str, str]
    sheet_result: SheetsLogResponse | None = None
    sheet_logged: bool = False
    already_recorded: bool = False
    progress: ThirdEyeCloseoutProgress | None = None
    message: str
    claude_calls: int = 0
