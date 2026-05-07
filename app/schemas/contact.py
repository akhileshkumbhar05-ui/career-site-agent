from typing import Optional
from pydantic import BaseModel


class RecruiterLookupRequest(BaseModel):
    company: str
    title: str
    location: Optional[str] = None


class RecruiterContact(BaseModel):
    name: str
    role: str
    source: str
    profile_url: str
    confidence: float


class RecruiterLookupResponse(BaseModel):
    company: str
    contacts: list[RecruiterContact]


class OutreachDraftRequest(BaseModel):
    company: str
    title: str
    recruiter_name: str


class OutreachDraftResponse(BaseModel):
    subject: str
    body: str
