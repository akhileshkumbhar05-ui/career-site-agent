from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.sheets import (
    APPLIED_USING_VALUES,
    SHEET_COLUMNS,
    STATUS_VALUES,
    SheetApplicationRow,
)


class ManualJDAnalyzeRequest(BaseModel):
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    jd_text: str = Field(min_length=20)
    link: str = ""
    location: str = ""
    salary_quoted: str = "N/A"
    source: str = "Unknown"
    applied_using: str = ""
    use_llm: bool = False


class SafeApplyPlan(BaseModel):
    recommendation: Literal["apply", "manual_review", "reject"]
    safe_autofill: dict[str, str]
    human_review_required: list[str]
    blocked_actions: list[str]
    submission_boundary: str


class ManualJDAnalyzeResponse(BaseModel):
    lead_id: str
    job: dict
    quality_gate: dict
    match: dict
    tailoring: dict
    apply_plan: SafeApplyPlan
    sheet_preview: dict[str, str]
    sheet_columns: tuple[str, ...] = SHEET_COLUMNS


class ConfirmApplicationLogRequest(BaseModel):
    lead_id: str = ""
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    link: str = ""
    salary_quoted: str = "N/A"
    source: str = "Unknown"
    applied_using: str = ""
    status: str = "Applied"
    date_applied: str = ""
    human_confirmed_submission: bool = False
    technical_issue: bool = False


class PrepareApplicationLogRequest(BaseModel):
    lead_id: str = ""
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    link: str = ""
    salary_quoted: str = "N/A"
    source: str = "Unknown"
    applied_using: str = ""
    technical_issue: bool = False


class PrepareApplicationLogResponse(BaseModel):
    success: bool
    action: Literal["ready", "duplicate"]
    message: str
    row: dict[str, str]
    duplicate_reason: Literal["link", "company_role"] | None = None
    requires_human_confirmation: bool = True
    audit_path: str = ""


class ConfirmApplicationLogResponse(BaseModel):
    success: bool
    action: Literal["created", "duplicate_skipped", "rejected", "write_failed"]
    message: str
    row: dict[str, str] | None = None
    audit_path: str = ""
    destination: Literal["google_sheets", "local_tracker", "none"] = "none"
