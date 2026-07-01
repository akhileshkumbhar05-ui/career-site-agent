from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.agent import RecruiterOutreachAgentRequest, RecruiterOutreachAgentResponse
from app.schemas.contact import OutreachDraftRequest, RecruiterLookupRequest
from app.services.recruiter_service import RecruiterService


class RecruiterOutreachAgent(BaseAgent):
    name = "recruiter_outreach"

    def __init__(self, *, recruiter: RecruiterService) -> None:
        self.recruiter = recruiter

    def run(self, payload: RecruiterOutreachAgentRequest) -> RecruiterOutreachAgentResponse:
        lookup = self.recruiter.find_recruiter(
            RecruiterLookupRequest(
                company=payload.company,
                title=payload.title,
                location=payload.location or None,
            )
        )
        contacts = lookup.contacts[: payload.max_contacts]
        drafts = [
            self.recruiter.draft_outreach(
                OutreachDraftRequest(
                    company=payload.company,
                    title=payload.title,
                    recruiter_name=contact.name,
                )
            )
            for contact in contacts
        ]
        return RecruiterOutreachAgentResponse(
            company=payload.company,
            contacts=contacts,
            drafts=drafts,
            steps=[
                self.step(
                    "find_and_draft",
                    f"Found {len(contacts)} recruiter search targets and drafted {len(drafts)} outreach notes.",
                )
            ],
        )
