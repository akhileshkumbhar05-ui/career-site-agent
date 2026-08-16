from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel


AppliedUsingValue = Literal[
    "LinkedIn",
    "Indeed",
    "Company Website",
    "ZipRecruiter",
    "Jobright.ai",
]

SheetStatus = Literal[
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
]

APPLIED_USING_VALUES: tuple[str, ...] = get_args(AppliedUsingValue)
STATUS_VALUES: tuple[str, ...] = get_args(SheetStatus)

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
