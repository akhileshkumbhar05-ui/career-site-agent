from typing import Optional
from pydantic import BaseModel


class ApplicationRowCreateRequest(BaseModel):
    company_applied: str
    role: str
    salary_quoted_while_applying: str = "N/A"
    job_posted_on: str = "Unknown"
    applied_using: str = "Company Website"
    status: str = "Applied"
    link: str = ""
    job_id: Optional[str] = None
    base_match_percent: Optional[int] = None
    tailored_match_percent: Optional[int] = None
    resume_version_used: Optional[str] = None
    notes: Optional[str] = None


class ApplicationStatusUpdateRequest(BaseModel):
    company_applied: str
    role: str
    status: str
    notes: Optional[str] = None


class ApplicationRowResponse(BaseModel):
    company_applied: str
    role: str
    status: str
    message: str


class ApplicationRow(BaseModel):
    company_applied: str
    role: str
    salary_quoted_while_applying: str
    job_posted_on: str
    applied_using: str
    status: str
    link: str
    job_id: Optional[str] = None
    base_match_percent: Optional[int] = None
    tailored_match_percent: Optional[int] = None
    resume_version_used: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SheetsLogRequest(BaseModel):
    date: Optional[str] = None
    company: str
    role: str
    salary: str = "N/A"
    job_posted_on: str = "Unknown"
    applied_using: str = "Company Website"
    status: str = "Applied"
    link: str = ""
    job_id: Optional[str] = None
    base_match_percent: Optional[int] = None
    tailored_match_percent: Optional[int] = None
    resume_version_used: Optional[str] = None
    notes: Optional[str] = None


class SheetsLogResponse(BaseModel):
    success: bool
    message: str
    script_version: Optional[str] = None
    mode: Optional[str] = None
    target_row: Optional[int] = None
