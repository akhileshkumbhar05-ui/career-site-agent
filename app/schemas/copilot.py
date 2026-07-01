from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


APPLIED_USING_VALUES = (
    "LinkedIn",
    "Indeed",
    "Company Website",
    "ZipRecruiter",
    "Jobright.ai",
)

STATUS_VALUES = (
    "Applied",
    "Screening Interview Call",
    "Technical Interview Call",
    "HR Interview Call",
    "Rejection",
    "Accepted/Offered Job",
    "Not Yet Applied Due to Technical Issue",
    "Cleared Automated Review",
    "ATS Rejection / Scope for Direct Contact",
    "Initial Rejection - Subject to further details",
)

SHEET_COLUMNS = (
    "Date",
    "Company Applied",
    "Role",
    "Salary Quoted while Applying",
    "Job Posted On",
    "Applied Using",
    "Status",
    "Link",
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


class SheetApplicationRow(BaseModel):
    date_applied: str
    company: str
    role: str
    salary_quoted: str
    source: str
    applied_using: str
    status: str
    job_url: str

    def as_legacy_sheet_row(self) -> dict[str, str]:
        return {
            "Date": self.date_applied,
            "Company Applied": self.company,
            "Role": self.role,
            "Salary Quoted while Applying": self.salary_quoted,
            "Job Posted On": self.source,
            "Applied Using": self.applied_using,
            "Status": self.status,
            "Link": self.job_url,
        }


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


class ConfirmApplicationLogResponse(BaseModel):
    success: bool
    action: Literal["created", "duplicate_skipped", "rejected"]
    message: str
    row: dict[str, str] | None = None
    audit_path: str = ""
