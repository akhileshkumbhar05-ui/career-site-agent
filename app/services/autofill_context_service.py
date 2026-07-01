from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.schemas.application_packet import ApplicationPacketExportRequest
from app.schemas.ats_autofill import AutofillContextRequest, AutofillContextResponse
from app.schemas.job import JDParseRequest, JobQualityGateRequest
from app.schemas.resume import ResumeDecisionRequest, ResumeScoreRequest, ResumeTailorRequest
from app.services.application_packet_export_service import ApplicationPacketExportService
from app.services.application_packet_service import ApplicationPacketService
from app.services.ats_autofill_service import ATSAutofillService
from app.services.decision_service import DecisionService
from app.services.jd_parser_service import JDParserService
from app.services.job_quality_gate_service import JobQualityGateService
from app.services.scoring_service import ScoringService
from app.services.tailoring_service import TailoringService


class AutofillContextService:
    """Creates the browser autofill context and prepares a tailored resume when needed.

    This service deliberately avoids the tracker. Opening an ATS page should not log an
    application to Google Sheets or local tracking until the user confirms submission.
    """

    def __init__(
        self,
        *,
        autofill: ATSAutofillService,
        parser: JDParserService,
        scorer: ScoringService,
        tailorer: TailoringService,
        decider: DecisionService,
        quality_gate: JobQualityGateService,
        packet_builder: ApplicationPacketService,
        packet_exporter: ApplicationPacketExportService,
    ) -> None:
        self.autofill = autofill
        self.parser = parser
        self.scorer = scorer
        self.tailorer = tailorer
        self.decider = decider
        self.quality_gate = quality_gate
        self.packet_builder = packet_builder
        self.packet_exporter = packet_exporter

    def load_or_prepare(self, payload: AutofillContextRequest) -> AutofillContextResponse:
        matched = self.autofill.load_context_for_url(payload.url)
        if matched.source == "matched_apply_plan" and not payload.force_prepare:
            return matched

        page_text = self._clean_page_text(payload.page_text)[: payload.max_page_text_chars]
        if payload.force_prepare and (len(page_text) < 800 or not self._has_job_description_signal(page_text)):
            fetched_page_text = self._fetch_page_text(payload.url)
            if len(fetched_page_text) > len(page_text):
                page_text = fetched_page_text[: payload.max_page_text_chars]
        page_identity = self._infer_page_identity(payload.page_title, payload.url, page_text)
        company = payload.company.strip() or page_identity["company"]
        role = payload.role.strip() or page_identity["role"]
        location = page_identity["location"]

        if not page_text or not role:
            if matched.source == "matched_apply_plan" and matched.prepared_resume_path:
                matched.message += (
                    " Using the existing matched tailored resume because the browser did not send enough "
                    "job-description text to refresh tailoring from this page."
                )
                return matched
            matched.message += " Could not prepare a tailored resume because the page text or role was unavailable."
            return matched

        if not self._has_job_description_signal(page_text):
            if matched.source == "matched_apply_plan" and matched.prepared_resume_path:
                matched.message += (
                    " Using the existing matched tailored resume because the browser did not send enough "
                    "job-description text to refresh tailoring from this page."
                )
                return matched
            matched.message += (
                " This page looks like an application form rather than the full job description, "
                "so no tailored resume was generated. Open the original job description page first "
                "or use an already processed packet for job-specific tailoring."
            )
            return matched

        gate = self.quality_gate.evaluate(
            JobQualityGateRequest(
                company=company,
                title=role,
                jd_text=page_text,
                location=location,
                source=payload.source,
            )
        )
        if gate.decision == "reject":
            hard_blockers = self._manual_tailor_blockers(gate.blockers)
            can_override_soft_title_reject = payload.force_prepare and not hard_blockers
            if can_override_soft_title_reject:
                gate.blockers = []
            else:
                detail = "; ".join(gate.blockers or gate.reasons)
                matched.message += (
                    " This page was not tailored because it failed the job quality gate"
                    f"{f': {detail}' if detail else '.'}"
                )
                return matched

        target_role_key = gate.role_key or self._infer_target_role_key(role, page_text)
        if gate.decision == "reject" and payload.force_prepare and not gate.blockers:
            gate.reasons = list(dict.fromkeys([*gate.reasons, "Manual Tailor Resume overrode a title-only discovery warning."]))

        # On an explicit Tailor request (force_prepare), do not let the hardcoded target-role
        # title allowlist block tailoring. Proceed with an empty role key and let the LLM
        # tailorer infer the role/summary from the job description itself.
        if gate.decision == "reject" and not target_role_key and not payload.force_prepare:
            detail = "; ".join(gate.blockers or gate.reasons)
            matched.message += (
                " This page was not tailored because it failed the job quality gate"
                f"{f': {detail}' if detail else '.'}"
            )
            return matched

        job_id = self._job_id_from_url(payload.url) or f"autofill_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        parsed = self.parser.parse(
            JDParseRequest(
                job_id=job_id,
                company=company,
                title=role,
                official_url=payload.url or None,
                jd_text=page_text,
            )
        )
        score = self.scorer.score(
            ResumeScoreRequest(
                job_id=job_id,
                resume_version="base_resume_v1",
                parsed_jd=parsed,
            )
        )
        tailored = self.tailorer.tailor(
            ResumeTailorRequest(
                job_id=job_id,
                resume_version="base_resume_v1",
                parsed_jd=parsed,
                current_score=score.overall_score,
                preferences=payload.tailoring_preferences,
            )
        )
        if not tailored.selected_project_ids and not tailored.summary_text:
            reason = "; ".join(tailored.changes_summary or ["This role was not worth tailoring."])
            matched.message += f" Tailored resume was not generated: {reason}"
            return matched
        decision = self.decider.decide(
            ResumeDecisionRequest(
                job_id=job_id,
                base_score=score.overall_score,
                tailored_score=tailored.tailored_score,
            )
        )

        packet = self.packet_builder.build(
            job_id=job_id,
            company=company,
            role=role,
            official_url=payload.url,
            base_score=int(score.overall_score),
            tailored_score=int(tailored.tailored_score),
            decision=decision.decision,
            decision_reason=decision.reason,
            target_role_key=target_role_key,
            source=payload.source,
            posted_at=None,
            location=location,
        )
        export = self.packet_exporter.export(
            ApplicationPacketExportRequest(
                application_packet=packet,
                output_root_override=payload.output_root_override,
                selected_project_ids=tailored.selected_project_ids,
                changes_summary=tailored.changes_summary or [decision.reason],
                summary_text=tailored.summary_text,
                rewritten_bullets=tailored.rewritten_bullets or [],
                connection_note=tailored.connection_note or "",
                jd_text=page_text,
                render_pdf=payload.render_pdf,
            )
        )

        apply_plan = self.autofill._load_json(export.apply_plan_path)
        resume_path = export.tailored_resume_docx_path or export.tailored_resume_pdf_path or export.tailored_resume_html_path
        message = "Prepared a tailored resume and apply plan from the current page without logging an application."
        if payload.force_prepare and gate.decision == "reject":
            message += " Manual Tailor Resume overrode a title-only discovery warning after checking hard blockers."
        if payload.render_pdf and not export.pdf_rendered:
            message += f" PDF rendering did not complete, so the HTML resume is shown instead: {export.pdf_error}"
        return AutofillContextResponse(
            source="prepared_tailored_resume",
            confidence=0.78,
            apply_plan=apply_plan,
            prepared_apply_plan_path=export.apply_plan_path,
            prepared_packet_folder_path=export.packet_folder_path,
            prepared_resume_path=resume_path,
            prepared_resume_docx_path=export.tailored_resume_docx_path,
            prepared_resume_html_path=export.tailored_resume_html_path,
            intended_resume_pdf_path=export.intended_tailored_resume_pdf_path,
            prepared_resume_pdf_path=export.tailored_resume_pdf_path or "",
            pdf_rendered=export.pdf_rendered,
            pdf_error=export.pdf_error,
            files_written=export.files_written,
            message=message,
            candidates=matched.candidates,
        )

    @staticmethod
    def _clean_page_text(value: str) -> str:
        text = re.sub(r"\s+", " ", value or "").strip()
        blocked_phrases = [
            "get notified for similar jobs",
            "accept cookies",
            "cookie preferences",
            "privacy policy",
        ]
        for phrase in blocked_phrases:
            text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _fetch_page_text(cls, url: str) -> str:
        parsed = urlparse(url or "")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
        }
        try:
            with httpx.Client(timeout=12.0, follow_redirects=True, headers=headers) as client:
                response = client.get(url)
                response.raise_for_status()
        except Exception:
            return ""
        return cls._extract_visible_text(response.text)

    @classmethod
    def _extract_visible_text(cls, html: str) -> str:
        soup = BeautifulSoup(html or "", "html.parser")
        for element in soup(["script", "style", "noscript", "svg"]):
            element.decompose()

        candidates = soup.select(
            "main, [role='main'], article, .job-description, #job-description, "
            ".content, .job-details, .careers-job-details"
        )
        text = " ".join(candidate.get_text(" ", strip=True) for candidate in candidates)
        if len(text) < 500:
            text = soup.get_text(" ", strip=True)
        return cls._clean_page_text(text)

    @classmethod
    def _infer_page_identity(cls, page_title: str, url: str, page_text: str) -> dict[str, str]:
        company = cls._infer_company(page_title, url, page_text)
        role = cls._infer_role(page_title, page_text)
        location = cls._infer_location(page_text)

        page_header = cls._infer_from_job_header(page_text)
        if page_header.get("company"):
            company = page_header["company"]
        if page_header.get("role"):
            role = page_header["role"]
        if page_header.get("location"):
            location = page_header["location"]

        return {
            "company": company or "Unknown Company",
            "role": role,
            "location": location,
        }

    @classmethod
    def _infer_company(cls, page_title: str, url: str, page_text: str) -> str:
        title = page_title or ""
        at_match = re.search(r"^(.+?)\s+at\s+(.+?)(?:\s[-|]\s|$)", title, flags=re.IGNORECASE)
        if at_match:
            candidate = cls._clean_title_piece(at_match.group(2))
            if candidate and not cls._looks_like_role(candidate):
                return candidate

        pieces = cls._title_parts(title)
        if len(pieces) >= 2:
            if cls._looks_like_role(pieces[1]) and not cls._looks_like_role(pieces[0]):
                return pieces[0]
            if cls._looks_like_role(pieces[0]) and not cls._looks_like_role(pieces[1]):
                return pieces[1]

        host_company = cls._company_from_host(url)
        if host_company:
            return host_company

        match = re.search(r"\bcompany\s*[:\-]\s*([A-Z][A-Za-z0-9 &.,'-]{2,60})", page_text)
        return match.group(1).strip() if match else "Unknown Company"

    @classmethod
    def _infer_role(cls, page_title: str, page_text: str) -> str:
        title = page_title.strip()
        if title:
            at_match = re.search(r"^(.+?)\s+at\s+.+?(?:\s[-|]\s|$)", title, flags=re.IGNORECASE)
            if at_match:
                candidate = cls._clean_title_piece(at_match.group(1))
                if cls._looks_like_role(candidate):
                    return candidate

            pieces = cls._title_parts(title)
            for piece in pieces:
                if cls._looks_like_role(piece):
                    return piece

        patterns = [
            r"\b(job title|role|position)\s*[:\-]\s*([A-Z][A-Za-z0-9 /,&+().'-]{3,120})",
            r"\b(apply for|application for)\s+([A-Z][A-Za-z0-9 /,&+().'-]{3,120})",
        ]
        for pattern in patterns:
            match = re.search(pattern, page_text, flags=re.IGNORECASE)
            if match:
                return match.group(2).strip()
        return ""

    @staticmethod
    def _infer_location(page_text: str) -> str:
        patterns = [
            r"\b(location|work location)\s*[:\-]\s*([A-Za-z ,.-]{2,80})",
            r"\b(Remote\s+Job|Remote|Hybrid|Onsite)\b",
            r"\b(Remote,\s*United States|United States|Arlington,\s*TX|Dallas,\s*TX|Austin,\s*TX)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, page_text, flags=re.IGNORECASE)
            if match:
                location = (match.group(2) if len(match.groups()) >= 2 else match.group(1)).strip()
                return "Remote" if location.lower() == "remote job" else location
        return ""

    @classmethod
    def _infer_from_job_header(cls, page_text: str) -> dict[str, str]:
        text = page_text[:1800]
        patterns = [
            (
                r"\b([A-Z][A-Za-z0-9 &.'-]{1,60})\s*\|\s*"
                r"(?:Full\s*time|Part\s*time|Contract|Internship)\s+"
                r"([A-Z][A-Za-z0-9 /,&+().'-]{3,90}?)\s+"
                r"(Remote\s+Job|Remote|Hybrid|Onsite|Posted\s+on)\b"
            ),
            (
                r"\b([A-Z][A-Za-z0-9 &.'-]{1,60})\s+"
                r"(?:is\s+hiring|hiring)\s+(?:a|an)?\s*"
                r"([A-Z][A-Za-z0-9 /,&+().'-]{3,90}?)\b"
            ),
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            company = cls._clean_title_piece(match.group(1))
            role = cls._clean_title_piece(match.group(2))
            location = ""
            if len(match.groups()) >= 3 and match.group(3):
                raw_location = match.group(3).strip()
                location = "Remote" if raw_location.lower() in {"remote", "remote job"} else raw_location
            if company and role and cls._looks_like_role(role):
                return {"company": company, "role": role, "location": location}
        return {}

    @staticmethod
    def _title_parts(title: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", (title or "").replace("–", "-")).strip()
        pieces = re.split(r"\s+\|\s+|\s+-\s+", normalized)
        return [AutofillContextService._clean_title_piece(piece) for piece in pieces if piece.strip()]

    @staticmethod
    def _clean_title_piece(value: str) -> str:
        cleaned = re.sub(r"\b(remote job|remote|hybrid|onsite|careers?|jobs?|job details|apply now)\b", " ", value, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|")
        return cleaned[:120].strip()

    @staticmethod
    def _looks_like_role(value: str) -> bool:
        lowered = value.lower()
        role_terms = (
            "analyst",
            "analytics",
            "business intelligence",
            "data",
            "engineer",
            "scientist",
            "machine learning",
            "ml",
            "ai",
            "artificial intelligence",
            "computer vision",
            "software",
            "developer",
            "product analyst",
        )
        return 3 <= len(value) <= 120 and any(term in lowered for term in role_terms)

    @staticmethod
    def _company_from_host(url: str) -> str:
        host = urlparse(url or "").netloc.lower()
        if not host:
            return ""
        parts = [part for part in host.split(".") if part and part not in {"www", "jobs", "careers"}]
        if not parts:
            return ""
        first = parts[0]
        if first in {"boards", "apply", "job-boards"} and len(parts) > 1:
            first = parts[1]
        return first.replace("-", " ").title()

    @staticmethod
    def _manual_tailor_blockers(blockers: list[str]) -> list[str]:
        return [
            blocker
            for blocker in blockers
            if "title does not match the configured target role families" not in blocker.lower()
        ]

    def _infer_target_role_key(self, role: str, page_text: str) -> str | None:
        combined = f"{role} {page_text[:1200]}".lower()
        for role_key, profile in self.scorer.role_profiles.items():
            aliases = [str(alias).lower() for alias in profile.get("title_aliases", [])]
            if any(alias and alias in combined for alias in aliases):
                return str(role_key)
        return None

    @staticmethod
    def _job_id_from_url(url: str) -> str:
        candidates = re.findall(r"\b[A-Z]{1,4}\d{4,}\b|\b\d{5,}\b", url or "")
        return candidates[-1] if candidates else ""

    @staticmethod
    def _has_job_description_signal(page_text: str) -> bool:
        normalized = page_text.lower()
        jd_markers = [
            "job description",
            "responsibilities",
            "requirements",
            "qualifications",
            "minimum qualifications",
            "preferred qualifications",
            "what you will do",
            "what you'll do",
            "about the role",
            "skills",
            "experience",
        ]
        skill_markers = [
            "python",
            "sql",
            "machine learning",
            "data science",
            "analytics",
            "model",
            "api",
            "pytorch",
            "tensorflow",
            "scikit",
        ]
        if any(marker in normalized for marker in jd_markers):
            return True
        return sum(1 for marker in skill_markers if marker in normalized) >= 3
