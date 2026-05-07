from typing import Optional, Literal
from pydantic import BaseModel

AppliedUsingLiteral = Literal["Company Website", "LinkedIn"]
ApplicationStatusLiteral = Literal["Applied", "Rejection", "Not Applied"]


class ApplicationRowCreateRequest(BaseModel):
    company_applied: str
    role: str
    salary_quoted_while_applying: str = "N/A"
    job_posted_on: str
    applied_using: AppliedUsingLiteral
    status: ApplicationStatusLiteral
    link: str
    job_id: Optional[str] = None
    base_match_percent: Optional[int] = None
    tailored_match_percent: Optional[int] = None
    resume_version_used: Optional[str] = None
    notes: Optional[str] = None


class ApplicationStatusUpdateRequest(BaseModel):
    company_applied: str
    role: str
    status: ApplicationStatusLiteral
    notes: Optional[str] = None


class ApplicationRowResponse(BaseModel):
    company_applied: str
    role: str
    status: ApplicationStatusLiteral
    message: str


class ApplicationRow(BaseModel):
    company_applied: str
    role: str
    salary_quoted_while_applying: str
    job_posted_on: str
    applied_using: AppliedUsingLiteral
    status: ApplicationStatusLiteral
    link: str
    job_id: Optional[str] = None
    base_match_percent: Optional[int] = None
    tailored_match_percent: Optional[int] = None
    resume_version_used: Optional[str] = None
    notes: Optional[str] = None