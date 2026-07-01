import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

from app.schemas.application_packet import ApplicationPacket


class ApplicationPacketService:
    def __init__(self, profile_path: str = "data/application_profile.json") -> None:
        self.profile = self._load_json(profile_path)

    def build(
        self,
        *,
        company: str,
        role: str,
        official_url: str,
        base_score: int,
        tailored_score: int | None,
        decision: str,
        decision_reason: str,
        target_role_key: str | None = None,
        job_id: str = "",
        source: str = "",
        posted_at: str | None = None,
        location: str | None = None,
    ) -> ApplicationPacket:
        resume_storage = self.profile.get("resume_storage", {})
        root_directory = resume_storage.get("root_directory", "D:\\Educational Documents\\Resumes")
        base_resume_pdf = resume_storage.get("base_resume_pdf", "")

        company_folder = self._sanitize_folder_name(company)
        role_slug = self._slugify(role)
        today = date.today().isoformat()
        filename = f"Akhilesh_Kumbhar_{company_folder}_{role_slug}_{today}.pdf"

        company_folder_path = str(Path(root_directory) / company_folder)
        tailored_resume_path = str(Path(company_folder_path) / filename)

        return ApplicationPacket(
            job_id=job_id,
            company=company,
            role=role,
            role_slug=role_slug,
            company_folder_path=company_folder_path,
            tailored_resume_path=tailored_resume_path,
            base_resume_pdf=base_resume_pdf,
            official_url=official_url,
            target_role_key=target_role_key,
            base_score=base_score,
            tailored_score=tailored_score,
            decision=decision,
            decision_reason=decision_reason,
            prefill_profile={
                "candidate": self.profile.get("candidate", {}),
                "work_authorization": self.profile.get("work_authorization", {}),
                "preferences": self.profile.get("preferences", {}),
            },
            human_control_note=self.profile.get("automation_boundary", {}).get(
                "submit_instruction",
                "Application portals may be prefilled, but final review and submission must remain manual.",
            ),
            source=source,
            posted_at=posted_at,
            location=location,
            ats_answer_bank=self._build_ats_answer_bank(),
            recruiter_searches=self._build_recruiter_searches(company, role, location),
            application_steps=self._build_application_steps(),
        )

    @staticmethod
    def _sanitize_folder_name(value: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*]+', " ", value).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned or "Unknown Company"

    @staticmethod
    def _slugify(value: str) -> str:
        lowered = value.lower()
        slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
        return slug[:80] or "role"

    def _build_ats_answer_bank(self) -> dict:
        candidate = self.profile.get("candidate", {})
        work_auth = self.profile.get("work_authorization", {})
        preferences = self.profile.get("preferences", {})

        return {
            "candidate": {
                "full_name": candidate.get("full_name", ""),
                "legal_first_name": candidate.get("legal_first_name") or candidate.get("first_name", ""),
                "legal_last_name": candidate.get("legal_last_name") or candidate.get("last_name", ""),
                "first_name": candidate.get("first_name") or candidate.get("legal_first_name", ""),
                "last_name": candidate.get("last_name") or candidate.get("legal_last_name", ""),
                "preferred_name": candidate.get("preferred_name", ""),
                "email": candidate.get("email", ""),
                "phone": candidate.get("phone", ""),
                "city": candidate.get("city", ""),
                "state": candidate.get("state", ""),
                "country": candidate.get("country", ""),
                "location": ", ".join(
                    item
                    for item in [
                        candidate.get("city", ""),
                        candidate.get("state", ""),
                        candidate.get("country", ""),
                    ]
                    if item
                ),
                "linkedin_url": candidate.get("linkedin_url") or candidate.get("linkedin", ""),
                "github_url": candidate.get("github_url") or candidate.get("github", ""),
            },
            "work_authorization": {
                "authorized_to_work_us_now": self._yes_no(work_auth.get("authorized_to_work_in_united_states")),
                "requires_sponsorship_now": self._yes_no(work_auth.get("requires_current_sponsorship")),
                "requires_sponsorship_future": self._yes_no(work_auth.get("requires_future_sponsorship")),
                "current_status": work_auth.get("current_status", ""),
                "opt_valid_until": work_auth.get("opt_valid_until", ""),
                "stem_opt_extension_available_months": work_auth.get("stem_opt_extension_available_months", ""),
                "standard_explanation": work_auth.get("standard_explanation", ""),
            },
            "preferences": {
                "willing_to_relocate": self._yes_no(preferences.get("willing_to_relocate")),
                "salary_filter_enabled": self._yes_no(preferences.get("salary_filter_enabled")),
                "target_level": preferences.get("target_level", ""),
            },
        }

    @staticmethod
    def _yes_no(value: object) -> str:
        if value is True:
            return "Yes"
        if value is False:
            return "No"
        return ""

    @staticmethod
    def _build_recruiter_searches(company: str, role: str, location: str | None) -> list[dict]:
        company_q = quote_plus(company)
        role_q = quote_plus(role)
        location_q = quote_plus(location or "United States")
        searches = [
            {
                "label": "LinkedIn company recruiters",
                "url": f"https://www.linkedin.com/search/results/people/?keywords={company_q}%20recruiter",
                "purpose": "Find talent acquisition or recruiter contacts at the company.",
            },
            {
                "label": "LinkedIn role-specific recruiters",
                "url": f"https://www.linkedin.com/search/results/people/?keywords={company_q}%20data%20science%20recruiter",
                "purpose": "Find recruiters closer to data, AI, ML, analytics, or engineering hiring.",
            },
            {
                "label": "LinkedIn hiring team search",
                "url": f"https://www.linkedin.com/search/results/people/?keywords={company_q}%20{role_q}%20hiring",
                "purpose": "Find likely hiring managers or team members connected to the role.",
            },
            {
                "label": "Google LinkedIn recruiter search",
                "url": f"https://www.google.com/search?q=site%3Alinkedin.com%2Fin+{company_q}+recruiter+{location_q}",
                "purpose": "Fallback external search when LinkedIn search results are thin.",
            },
        ]
        return searches

    @staticmethod
    def _build_application_steps() -> list[dict]:
        return [
            {
                "step": "review_packet",
                "owner": "human",
                "description": "Review score, resume PDF, JD, ATS answers, and outreach draft before opening the ATS.",
            },
            {
                "step": "prefill_application",
                "owner": "browser_assist",
                "description": "Use ATS answer bank and tailored resume PDF to fill the form where safe.",
            },
            {
                "step": "human_submit",
                "owner": "human",
                "description": "Final review and submit remain manual.",
            },
            {
                "step": "log_confirmed_application",
                "owner": "automation",
                "description": "After submission, call WF3 or /tracker/log-to-sheets to record the application.",
            },
            {
                "step": "recruiter_outreach",
                "owner": "human",
                "description": "Use recruiter search links and connection note draft to start outreach.",
            },
        ]

    @staticmethod
    def _load_json(path_str: str) -> dict:
        path = Path(path_str)
        return json.loads(path.read_text(encoding="utf-8"))
