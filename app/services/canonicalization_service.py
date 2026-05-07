from urllib.parse import urlparse

from app.schemas.job import (
    OfficialJobResolutionRequest,
    OfficialJobResolutionResponse,
)


class CanonicalizationService:
    ATS_HINTS = {
        "greenhouse": "greenhouse",
        "lever": "lever",
        "ashby": "ashby",
        "workday": "workday",
        "icims": "icims",
        "smartrecruiters": "smartrecruiters",
    }

    def resolve(
        self,
        payload: OfficialJobResolutionRequest,
    ) -> OfficialJobResolutionResponse:
        url = (payload.discovered_url or "").strip()

        if not url:
            return OfficialJobResolutionResponse(
                canonical_job_id=self._build_job_id(payload.company, payload.title),
                official_url="",
                ats_type="unknown",
                status="unresolved",
                confidence=0.0,
            )

        lowered = url.lower()
        domain = urlparse(url).netloc.lower()

        ats_type = self._detect_ats(lowered)
        official_status = self._is_likely_official(domain, payload.company)

        confidence = 0.55
        status = "needs_review"

        if official_status:
            confidence = 0.9 if ats_type != "unknown" else 0.8
            status = "live"
        elif any(board in domain for board in ["linkedin", "indeed", "ziprecruiter", "jobright"]):
            confidence = 0.35
            status = "aggregator_only"

        return OfficialJobResolutionResponse(
            canonical_job_id=self._build_job_id(payload.company, payload.title),
            official_url=url,
            ats_type=ats_type,
            status=status,
            confidence=confidence,
        )

    def _detect_ats(self, lowered_url: str) -> str:
        for hint, label in self.ATS_HINTS.items():
            if hint in lowered_url:
                return label
        return "unknown"

    @staticmethod
    def _build_job_id(company: str, title: str) -> str:
        company_key = "_".join(company.lower().split())
        title_key = "_".join(title.lower().split())
        return f"{company_key}_{title_key}"

    @staticmethod
    def _is_likely_official(domain: str, company: str) -> bool:
        company_tokens = [token for token in company.lower().split() if len(token) > 2]
        if any(token in domain for token in company_tokens):
            return True

        trusted_ats_domains = [
            "greenhouse.io",
            "lever.co",
            "ashbyhq.com",
            "myworkdayjobs.com",
            "icims.com",
            "smartrecruiters.com",
        ]
        return any(trusted in domain for trusted in trusted_ats_domains)