from app.schemas.contact import (
    OutreachDraftRequest,
    OutreachDraftResponse,
    RecruiterContact,
    RecruiterLookupRequest,
    RecruiterLookupResponse,
)


class RecruiterService:
    def find_recruiter(self, payload: RecruiterLookupRequest) -> RecruiterLookupResponse:
        contacts = [
            RecruiterContact(
                name=f"{payload.company} Talent Acquisition",
                role="Talent Acquisition",
                source="company careers page",
                profile_url=f"https://www.linkedin.com/search/results/people/?keywords={payload.company}%20recruiter",
                confidence=0.55,
            )
        ]
        return RecruiterLookupResponse(company=payload.company, contacts=contacts)

    def draft_outreach(self, payload: OutreachDraftRequest) -> OutreachDraftResponse:
        subject = f"Interest in {payload.title} at {payload.company}"
        body = (
            f"Hi {payload.recruiter_name},\n\n"
            f"I recently came across the {payload.title} role at {payload.company} and wanted to reach out. "
            "My background includes applied machine learning, analytics, and deployment-focused AI systems. "
            "I would value the opportunity to learn more about what the team is looking for in strong candidates.\n\n"
            "Best regards,\nAkhilesh Kumbhar"
        )
        return OutreachDraftResponse(subject=subject, body=body)
