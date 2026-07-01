from __future__ import annotations

import re
import json
from collections import defaultdict
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from app.schemas.ats_autofill import (
    AutofillContextCandidate,
    AutofillContextResponse,
    AutofillField,
    AutofillMatch,
    AutofillPlan,
)


US_STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}


@dataclass(frozen=True)
class AnswerCandidate:
    key: str
    value: str
    confidence: float
    reason: str


class ATSAutofillService:
    """Builds a guarded autofill plan for job application pages.

    The service is intentionally conservative: it fills high-confidence
    profile/work-authorization fields and refuses sensitive, ambiguous, or
    final-submit related controls.
    """

    EEO_TERMS = (
        "eeo",
        "equal employment",
        "gender",
        "sex",
        "race",
        "ethnicity",
        "hispanic",
        "latino",
        "veteran",
        "disability",
        "self-identification",
        "voluntary self",
        "pronouns",
    )
    SENSITIVE_TERMS = (
        "social security",
        "ssn",
        "date of birth",
        "birth date",
        "dob",
        "password",
        "signature",
        "driver license",
        "driver's license",
        "background check",
    )
    CITIZENSHIP_CLEARANCE_TERMS = (
        "us citizen",
        "u.s. citizen",
        "united states citizen",
        "citizenship",
        "security clearance",
        "clearance",
    )
    MONEY_TERMS = ("salary", "compensation", "desired pay", "expected pay", "hourly rate")
    SUBMIT_TERMS = ("submit", "apply", "send application", "certify and submit")

    def __init__(
        self,
        profile_path: str = "data/application_profile.json",
        apply_plan_roots: list[str] | None = None,
    ) -> None:
        self.profile_path = Path(profile_path)
        self.apply_plan_roots = [
            Path(root)
            for root in (
                apply_plan_roots
                or [
                    "data/outputs/autofill_packets",
                    "data/outputs/agent_packets",
                    "data/outputs/queue_packets",
                    "data/outputs/queue_packets_test",
                    "data/outputs/n8n_packet_test",
                ]
            )
        ]

    def load_context_for_url(self, page_url: str = "") -> AutofillContextResponse:
        candidates = self._find_apply_plan_candidates(page_url)
        if candidates:
            best = candidates[0]
            if best.score >= 0.82:
                apply_plan = self._load_json(best.apply_plan_path)
                resume_artifacts = self._resume_artifacts_from_apply_plan(apply_plan)
                return AutofillContextResponse(
                    source="matched_apply_plan",
                    confidence=best.score,
                    apply_plan=apply_plan,
                    matched_apply_plan_path=best.apply_plan_path,
                    prepared_apply_plan_path=best.apply_plan_path,
                    prepared_packet_folder_path=str(Path(best.apply_plan_path).parent),
                    prepared_resume_path=resume_artifacts["resume_path"],
                    prepared_resume_docx_path=resume_artifacts["docx_path"],
                    prepared_resume_html_path=resume_artifacts["html_path"],
                    intended_resume_pdf_path=resume_artifacts["intended_pdf_path"],
                    prepared_resume_pdf_path=resume_artifacts["pdf_path"],
                    pdf_rendered=bool(resume_artifacts["pdf_path"]),
                    message="Matched current page URL to a generated application plan.",
                    candidates=candidates[:5],
                )

        return AutofillContextResponse(
            source="profile_fallback",
            confidence=0.5,
            apply_plan=self._build_profile_fallback_apply_plan(page_url),
            message=(
                "No high-confidence job-specific apply_plan.json was found for this page. "
                "Using local profile answers for safe basic fields."
            ),
            candidates=candidates[:5],
        )

    @staticmethod
    def _resume_artifacts_from_apply_plan(apply_plan: dict[str, Any]) -> dict[str, str]:
        resume = apply_plan.get("resume") if isinstance(apply_plan.get("resume"), dict) else {}
        tailored_path = str(resume.get("tailored_resume_path") or "")
        docx_path = str(resume.get("tailored_resume_docx_path") or "")
        html_path = str(resume.get("tailored_resume_html_path") or "")
        intended_pdf_path = str(resume.get("intended_tailored_resume_pdf_path") or "")
        pdf_path = str(resume.get("tailored_resume_pdf_path") or "")

        if not intended_pdf_path and tailored_path.lower().endswith(".pdf"):
            intended_pdf_path = tailored_path
        if not pdf_path and tailored_path.lower().endswith(".pdf") and ATSAutofillService._path_exists(tailored_path):
            pdf_path = tailored_path

        existing_resume_path = ""
        for candidate in (docx_path, tailored_path, pdf_path, html_path):
            if ATSAutofillService._path_exists(candidate):
                existing_resume_path = candidate
                break
        if not existing_resume_path:
            existing_resume_path = docx_path or pdf_path or html_path or tailored_path

        return {
            "resume_path": existing_resume_path,
            "docx_path": docx_path if ATSAutofillService._path_exists(docx_path) else "",
            "html_path": html_path,
            "intended_pdf_path": intended_pdf_path,
            "pdf_path": pdf_path if ATSAutofillService._path_exists(pdf_path) else "",
        }

    @staticmethod
    def _path_exists(value: str) -> bool:
        if not value:
            return False
        try:
            return Path(value).exists()
        except (OSError, ValueError):
            return False

    def build_profile_apply_plan(self, page_url: str = "", job: dict[str, Any] | None = None) -> dict[str, Any]:
        apply_plan = self._build_profile_fallback_apply_plan(page_url)
        if not job:
            return apply_plan

        target_url = str(
            job.get("discovered_url")
            or job.get("official_url")
            or job.get("url")
            or job.get("link")
            or page_url
            or ""
        )
        apply_plan["job"].update(
            {
                "job_id": str(job.get("job_id") or job.get("id") or ""),
                "company": str(job.get("company") or ""),
                "role": str(job.get("title") or job.get("role") or ""),
                "official_url": target_url,
                "source": str(job.get("source") or "profile_autofill"),
                "posted_at": job.get("posted_at"),
                "location": str(job.get("location") or ""),
            }
        )
        apply_plan["decision"].update(
            {
                "reason": "Using saved application profile answers; tailored packet generation is optional.",
                "base_score": job.get("base_score") or job.get("ai_base_score") or job.get("score"),
                "tailored_score": job.get("tailored_score") or job.get("ai_score"),
                "target_role_key": job.get("quality_role_key") or job.get("target_role_key"),
            }
        )
        existing_resume_path = str(
            job.get("tailored_resume_docx_path")
            or job.get("prepared_resume_docx_path")
            or job.get("tailored_resume_pdf_path")
            or job.get("tailored_resume_path")
            or job.get("prepared_resume_path")
            or ""
        )
        if existing_resume_path:
            apply_plan["resume"]["tailored_resume_path"] = existing_resume_path
            if existing_resume_path.lower().endswith(".docx"):
                apply_plan["resume"]["tailored_resume_docx_path"] = existing_resume_path
        return apply_plan

    def extract_fields_from_html(self, html: str) -> list[AutofillField]:
        soup = BeautifulSoup(html, "html.parser")
        fields: list[AutofillField] = []

        radio_groups: dict[str, list[Tag]] = defaultdict(list)
        for element in soup.find_all(["input", "select", "textarea"]):
            if not isinstance(element, Tag):
                continue
            if self._is_non_application_control(element):
                continue
            input_type = str(element.get("type", "")).lower() or element.name
            if input_type == "radio":
                radio_groups[str(element.get("name") or element.get("id") or "radio")].append(element)
                continue

            fields.append(self._field_from_element(soup, element, len(fields) + 1))

        for group_name, options in radio_groups.items():
            fields.append(self._field_from_radio_group(soup, group_name, options, len(fields) + 1))

        return fields

    def build_plan_from_html(self, html: str, apply_plan: dict[str, Any], source_url: str = "") -> AutofillPlan:
        return self.build_plan(self.extract_fields_from_html(html), apply_plan, source_url=source_url)

    def build_plan(
        self,
        fields: list[AutofillField],
        apply_plan: dict[str, Any],
        source_url: str = "",
    ) -> AutofillPlan:
        answers = self._build_answer_catalog(apply_plan)
        matches = [self._match_field(field, answers) for field in fields]
        fillable = [match for match in matches if match.action in {"fill_text", "select_option", "choose_radio"}]
        manual = [match for match in matches if match.action in {"manual_review", "manual_upload"}]
        skipped = [match for match in matches if match.action in {"skip_sensitive", "skip_unknown"}]

        return AutofillPlan(
            source_url=source_url,
            total_fields=len(fields),
            fillable_count=len(fillable),
            manual_count=len(manual),
            skipped_count=len(skipped),
            matches=matches,
        )

    def _find_apply_plan_candidates(self, page_url: str) -> list[AutofillContextCandidate]:
        if not page_url:
            return []

        candidates: list[AutofillContextCandidate] = []
        for root in self.apply_plan_roots:
            if not root.exists():
                continue
            for path in root.rglob("apply_plan.json"):
                try:
                    apply_plan = self._load_json(str(path))
                except Exception:
                    continue

                job = apply_plan.get("job") or {}
                score = self._score_apply_plan_url_match(page_url, job)
                if score <= 0:
                    continue
                candidates.append(
                    AutofillContextCandidate(
                        company=str(job.get("company") or ""),
                        role=str(job.get("role") or ""),
                        official_url=str(job.get("official_url") or ""),
                        apply_plan_path=str(path),
                        score=score,
                    )
                )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates

    def _score_apply_plan_url_match(self, page_url: str, job: dict[str, Any]) -> float:
        official_url = str(job.get("official_url") or "")
        job_id = str(job.get("job_id") or "")
        company = str(job.get("company") or "")
        role = str(job.get("role") or "")

        normalized_page = self._normalize_url(page_url)
        normalized_official = self._normalize_url(official_url)
        page_text = self._normalize(page_url)
        official_text = self._normalize(official_url)

        if normalized_page and normalized_official and normalized_page == normalized_official:
            return 1.0
        if job_id and self._normalize(job_id) in page_text:
            return 0.96
        if normalized_official and normalized_page.startswith(normalized_official):
            return 0.92
        if official_text and official_text in page_text:
            return 0.9

        page_host = urlparse(page_url).netloc.lower()
        official_host = urlparse(official_url).netloc.lower()
        page_path = urlparse(page_url).path.lower()
        official_path = urlparse(official_url).path.lower()
        score = 0.0

        if page_host and official_host and page_host == official_host:
            score = max(score, 0.66)
        elif page_host and official_host and (
            page_host.endswith(official_host) or official_host.endswith(page_host)
        ):
            score = max(score, 0.62)

        company_tokens = self._meaningful_tokens(company)
        company_matches = bool(company_tokens and any(token in page_text for token in company_tokens))
        if company_matches:
            score = max(score, 0.7)

        official_tail = official_path.rstrip("/").split("/")[-1]
        tail_has_identifier = bool(
            re.search(r"\d", official_tail)
            or (job_id and self._normalize(job_id) in self._normalize(official_tail))
            or company_matches
            or (page_host and official_host and page_host == official_host)
        )
        if official_tail and official_tail in page_path and tail_has_identifier:
            score = max(score, 0.82)

        role_tokens = self._meaningful_tokens(role)
        if role_tokens:
            overlap = sum(1 for token in role_tokens if token in page_text)
            if company_matches and overlap >= min(3, len(role_tokens)):
                score = max(score, 0.84)
            elif company_matches and overlap >= 2:
                score = max(score, 0.74)

        return score

    def _build_profile_fallback_apply_plan(self, page_url: str) -> dict[str, Any]:
        profile = self._load_json(str(self.profile_path)) if self.profile_path.exists() else {}
        candidate = profile.get("candidate") or {}
        work_auth = profile.get("work_authorization") or {}
        preferences = profile.get("preferences") or {}
        resume_storage = profile.get("resume_storage") or {}

        return {
            "job": {
                "job_id": "",
                "company": "",
                "role": "",
                "official_url": page_url,
                "source": "browser_profile_fallback",
                "posted_at": None,
                "location": "",
            },
            "decision": {
                "decision": "manual_review",
                "reason": "No job-specific apply plan was matched; using profile-only autofill.",
                "base_score": None,
                "tailored_score": None,
                "target_role_key": None,
            },
            "resume": {
                "base_resume_pdf": resume_storage.get("base_resume_pdf", ""),
                "tailored_resume_path": "",
                "tailored_resume_docx_path": "",
                "selected_project_ids": [],
                "summary_text": None,
                "rewritten_bullets": [],
                "changes_summary": [],
            },
            "ats_answer_bank": {
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
                    "authorized_to_work_us_now": self._yes_no(
                        work_auth.get("authorized_to_work_in_united_states")
                    ),
                    "requires_sponsorship_now": self._yes_no(work_auth.get("requires_current_sponsorship")),
                    "requires_sponsorship_future": self._yes_no(work_auth.get("requires_future_sponsorship")),
                    "current_status": work_auth.get("current_status", ""),
                    "opt_valid_until": work_auth.get("opt_valid_until", ""),
                    "stem_opt_extension_available_months": work_auth.get(
                        "stem_opt_extension_available_months",
                        "",
                    ),
                    "standard_explanation": work_auth.get("standard_explanation", ""),
                },
                "preferences": {
                    "willing_to_relocate": self._yes_no(preferences.get("willing_to_relocate")),
                    "salary_filter_enabled": self._yes_no(preferences.get("salary_filter_enabled")),
                    "target_level": preferences.get("target_level", ""),
                },
            },
            "human_control": {
                "allow_final_submit": False,
                "note": profile.get("automation_boundary", {}).get(
                    "submit_instruction",
                    "Application portals may be prefilled, but final review and submission must remain manual.",
                ),
            },
        }

    def _field_from_element(self, soup: BeautifulSoup, element: Tag, index: int) -> AutofillField:
        input_type = str(element.get("type", "")).lower() or element.name or ""
        label = self._label_for_element(soup, element)
        options: list[str] = []
        if element.name == "select":
            options = [
                self._clean_text(option.get_text(" ", strip=True) or str(option.get("value") or ""))
                for option in element.find_all("option")
            ]

        return AutofillField(
            field_id=self._element_field_id(element, index),
            selector=self._selector_for_element(element),
            tag=str(element.name or ""),
            input_type=input_type,
            label=label,
            name=str(element.get("name") or ""),
            id_attr=str(element.get("id") or ""),
            placeholder=str(element.get("placeholder") or ""),
            aria_label=str(element.get("aria-label") or ""),
            required=element.has_attr("required") or str(element.get("aria-required", "")).lower() == "true",
            options=[option for option in options if option],
            context=self._context_for_element(element),
        )

    def _field_from_radio_group(
        self,
        soup: BeautifulSoup,
        group_name: str,
        elements: list[Tag],
        index: int,
    ) -> AutofillField:
        labels = [self._label_for_element(soup, element) for element in elements]
        group_label = self._radio_group_label(elements[0]) if elements else ""
        options = [
            self._clean_text(label or str(element.get("value") or ""))
            for label, element in zip(labels, elements, strict=False)
        ]
        return AutofillField(
            field_id=f"radio:{group_name or index}",
            selector=f'input[type="radio"][name="{group_name}"]',
            tag="input",
            input_type="radio_group",
            label=group_label or self._clean_text(" / ".join(labels)),
            name=group_name,
            required=any(element.has_attr("required") for element in elements),
            options=[option for option in options if option],
            context=self._context_for_element(elements[0]) if elements else "",
        )

    def _match_field(self, field: AutofillField, answers: dict[str, str]) -> AutofillMatch:
        field_text = self._field_text(field)
        normalized = self._normalize(field_text)

        if self._contains_any(normalized, self.SUBMIT_TERMS):
            return self._match(field, "skip_sensitive", reason="Submit/apply controls are never automated.")
        if self._contains_any(normalized, self.EEO_TERMS):
            return self._match(field, "skip_sensitive", reason="EEO/demographic fields are left for manual review.")
        if self._contains_any(normalized, self.SENSITIVE_TERMS):
            return self._match(field, "skip_sensitive", reason="Sensitive identity/security fields are not autofilled.")
        if self._contains_any(normalized, self.CITIZENSHIP_CLEARANCE_TERMS):
            return self._match(
                field,
                "manual_review",
                reason="Citizenship or clearance questions should be reviewed before continuing.",
            )
        if self._contains_any(normalized, self.MONEY_TERMS):
            return self._match(field, "manual_review", reason="Compensation fields are not configured yet.")

        candidate = self._candidate_answer(field, normalized, answers)
        if candidate:
            return self._build_field_match(field, candidate)

        work_auth = self._work_authorization_answer(field, normalized, answers)
        if work_auth:
            return self._build_field_match(field, work_auth)

        preference = self._preference_answer(field, normalized, answers)
        if preference:
            return self._build_field_match(field, preference)

        if "cover letter" in normalized:
            return self._match(field, "manual_review", reason="Cover letter fields need job-specific review.")
        if field.input_type == "checkbox":
            return self._match(field, "manual_review", reason="Checkbox attestations are left unchecked by default.")

        return self._match(field, "skip_unknown", reason="No high-confidence mapping was found.")

    def _candidate_answer(
        self,
        field: AutofillField,
        normalized: str,
        answers: dict[str, str],
    ) -> AnswerCandidate | None:
        if "first name" in normalized or "given name" in normalized:
            return self._candidate("candidate.first_name", answers, 0.96, "Matched first name field.")
        if "last name" in normalized or "family name" in normalized or "surname" in normalized:
            return self._candidate("candidate.last_name", answers, 0.96, "Matched last name field.")
        if self._has_word(normalized, "name") and not self._contains_any(normalized, ("company", "employer", "school")):
            return self._candidate("candidate.full_name", answers, 0.9, "Matched full name field.")
        if "email" in normalized:
            return self._candidate("candidate.email", answers, 0.98, "Matched email field.")
        if "phone" in normalized or "mobile" in normalized or "telephone" in normalized:
            return self._candidate("candidate.phone", answers, 0.96, "Matched phone field.")
        if "linkedin" in normalized or "linked in" in normalized:
            return self._candidate("candidate.linkedin_url", answers, 0.97, "Matched LinkedIn profile field.")
        if "github" in normalized or "git hub" in normalized:
            return self._candidate("candidate.github_url", answers, 0.97, "Matched GitHub profile field.")
        if "portfolio" in normalized or "personal website" in normalized or "website url" in normalized:
            return self._candidate("candidate.github_url", answers, 0.78, "Using GitHub URL for portfolio/website field.")
        if field.input_type == "file" and self._contains_any(normalized, ("resume", "cv", "curriculum vitae")):
            return self._candidate("resume.tailored_resume_path", answers, 0.95, "Resume/CV upload field detected.")
        if self._has_word(normalized, "city"):
            return self._candidate("candidate.city", answers, 0.9, "Matched city field.")
        if self._has_word(normalized, "state") or self._has_word(normalized, "province"):
            return self._candidate("candidate.state", answers, 0.86, "Matched state/province field.")
        if self._has_word(normalized, "country"):
            return self._candidate("candidate.country", answers, 0.92, "Matched country field.")
        if "current location" in normalized or "location" == normalized.strip():
            return self._candidate("candidate.location", answers, 0.84, "Matched current location field.")
        return None

    def _work_authorization_answer(
        self,
        field: AutofillField,
        normalized: str,
        answers: dict[str, str],
    ) -> AnswerCandidate | None:
        if "authorized" in normalized and "work" in normalized:
            return self._candidate(
                "work_authorization.authorized_to_work_us_now",
                answers,
                0.95,
                "Matched current work authorization question.",
            )
        if "legally authorized" in normalized:
            return self._candidate(
                "work_authorization.authorized_to_work_us_now",
                answers,
                0.95,
                "Matched legal work authorization question.",
            )
        if self._contains_any(normalized, ("sponsor", "sponsorship", "visa")):
            if "future" in normalized or "now or" in normalized or "currently or" in normalized:
                return self._candidate(
                    "work_authorization.requires_sponsorship_future",
                    answers,
                    0.9,
                    "Matched now-or-future sponsorship question.",
                )
            if "current" in normalized or "now" in normalized:
                return self._candidate(
                    "work_authorization.requires_sponsorship_now",
                    answers,
                    0.9,
                    "Matched current sponsorship question.",
                )
            return AnswerCandidate(
                key="",
                value="",
                confidence=0.0,
                reason="Sponsorship wording is ambiguous; review before answering.",
            )
        if "work authorization status" in normalized or "visa status" in normalized:
            return self._candidate(
                "work_authorization.current_status",
                answers,
                0.86,
                "Matched work authorization status field.",
            )
        return None

    def _preference_answer(
        self,
        field: AutofillField,
        normalized: str,
        answers: dict[str, str],
    ) -> AnswerCandidate | None:
        if "relocat" in normalized:
            return self._candidate("preferences.willing_to_relocate", answers, 0.93, "Matched relocation preference.")
        return None

    def _build_field_match(self, field: AutofillField, candidate: AnswerCandidate) -> AutofillMatch:
        if not candidate.key:
            return self._match(field, "manual_review", reason=candidate.reason)

        if field.input_type == "file":
            return self._match(
                field,
                "manual_upload",
                answer_key=candidate.key,
                answer_value=candidate.value,
                confidence=candidate.confidence,
                reason=candidate.reason,
            )

        if field.input_type == "radio_group":
            target = self._best_option(candidate.value, field.options)
            if not target:
                return self._match(
                    field,
                    "manual_review",
                    answer_key=candidate.key,
                    answer_value=candidate.value,
                    confidence=max(candidate.confidence - 0.3, 0.0),
                    reason=f"{candidate.reason} No matching radio option was found.",
                )
            return self._match(
                field,
                "choose_radio",
                answer_key=candidate.key,
                answer_value=candidate.value,
                target_option=target,
                confidence=candidate.confidence,
                reason=candidate.reason,
            )

        if field.tag == "select":
            target = self._best_option(candidate.value, field.options)
            if not target:
                return self._match(
                    field,
                    "manual_review",
                    answer_key=candidate.key,
                    answer_value=candidate.value,
                    confidence=max(candidate.confidence - 0.35, 0.0),
                    reason=f"{candidate.reason} No matching select option was found.",
                )
            return self._match(
                field,
                "select_option",
                answer_key=candidate.key,
                answer_value=candidate.value,
                target_option=target,
                confidence=candidate.confidence,
                reason=candidate.reason,
            )

        return self._match(
            field,
            "fill_text",
            answer_key=candidate.key,
            answer_value=candidate.value,
            confidence=candidate.confidence,
            reason=candidate.reason,
        )

    def _build_answer_catalog(self, apply_plan: dict[str, Any]) -> dict[str, str]:
        bank = apply_plan.get("ats_answer_bank") or {}
        candidate = bank.get("candidate") or {}
        work_auth = bank.get("work_authorization") or {}
        preferences = bank.get("preferences") or {}
        resume = apply_plan.get("resume") or {}

        full_name = str(candidate.get("full_name") or "")
        parts = full_name.split()
        inferred_first = " ".join(parts[:-1]) if len(parts) > 2 else (parts[0] if parts else "")
        profile_first = str(candidate.get("first_name") or "")
        if not candidate.get("legal_first_name") and len(parts) > 2 and profile_first == parts[0]:
            profile_first = inferred_first
        first_name = str(
            candidate.get("legal_first_name")
            or profile_first
            or inferred_first
        )
        last_name = str(
            candidate.get("legal_last_name")
            or candidate.get("last_name")
            or (parts[-1] if len(parts) > 1 else "")
        )
        state = str(candidate.get("state") or "")

        answers = {
            "candidate.full_name": full_name,
            "candidate.first_name": first_name,
            "candidate.last_name": last_name,
            "candidate.legal_first_name": first_name,
            "candidate.legal_last_name": last_name,
            "candidate.preferred_name": str(candidate.get("preferred_name") or first_name),
            "candidate.email": str(candidate.get("email") or ""),
            "candidate.phone": str(candidate.get("phone") or ""),
            "candidate.location": str(candidate.get("location") or ""),
            "candidate.city": str(candidate.get("city") or ""),
            "candidate.state": state,
            "candidate.state_name": US_STATE_NAMES.get(state.upper(), state),
            "candidate.country": str(candidate.get("country") or "United States"),
            "candidate.linkedin_url": str(candidate.get("linkedin_url") or ""),
            "candidate.github_url": str(candidate.get("github_url") or ""),
            "work_authorization.authorized_to_work_us_now": str(
                work_auth.get("authorized_to_work_us_now") or ""
            ),
            "work_authorization.requires_sponsorship_now": str(
                work_auth.get("requires_sponsorship_now") or ""
            ),
            "work_authorization.requires_sponsorship_future": str(
                work_auth.get("requires_sponsorship_future") or ""
            ),
            "work_authorization.current_status": str(work_auth.get("current_status") or ""),
            "work_authorization.standard_explanation": str(
                work_auth.get("standard_explanation") or ""
            ),
            "preferences.willing_to_relocate": str(preferences.get("willing_to_relocate") or ""),
            "resume.tailored_resume_path": str(
                resume.get("tailored_resume_path") or resume.get("base_resume_pdf") or ""
            ),
        }
        return {key: value for key, value in answers.items() if value}

    def _candidate(
        self,
        key: str,
        answers: dict[str, str],
        confidence: float,
        reason: str,
    ) -> AnswerCandidate | None:
        value = answers.get(key)
        if not value and key == "candidate.state":
            value = answers.get("candidate.state_name")
        if not value:
            return None
        return AnswerCandidate(key=key, value=value, confidence=confidence, reason=reason)

    def _best_option(self, answer: str, options: list[str]) -> str:
        if not answer or not options:
            return ""
        normalized_answer = self._normalize(answer)
        answer_synonyms = {normalized_answer}
        if normalized_answer in {"yes", "true"}:
            answer_synonyms.update({"yes", "y"})
        if normalized_answer in {"no", "false"}:
            answer_synonyms.update({"no", "n"})
        if normalized_answer in {"united states", "usa", "us", "u s"}:
            answer_synonyms.update({"united states", "united states of america", "usa", "us"})
        if len(answer) == 2 and answer.upper() in US_STATE_NAMES:
            answer_synonyms.add(self._normalize(US_STATE_NAMES[answer.upper()]))

        for option in options:
            normalized_option = self._normalize(option)
            if normalized_option in answer_synonyms:
                return option
        for option in options:
            normalized_option = self._normalize(option)
            if any(synonym and synonym in normalized_option for synonym in answer_synonyms):
                return option
        return ""

    def _match(
        self,
        field: AutofillField,
        action: str,
        answer_key: str = "",
        answer_value: str = "",
        target_option: str = "",
        confidence: float = 0.0,
        reason: str = "",
    ) -> AutofillMatch:
        return AutofillMatch(
            field=field,
            action=action,
            answer_key=answer_key,
            answer_value=answer_value,
            target_option=target_option,
            confidence=confidence,
            reason=reason,
        )

    def _label_for_element(self, soup: BeautifulSoup, element: Tag) -> str:
        element_id = element.get("id")
        if element_id:
            label = soup.find("label", attrs={"for": element_id})
            if isinstance(label, Tag):
                return self._clean_text(label.get_text(" ", strip=True))

        parent_label = element.find_parent("label")
        if isinstance(parent_label, Tag):
            text = parent_label.get_text(" ", strip=True)
            value = str(element.get("value") or "")
            if value:
                text = text.replace(value, " ")
            return self._clean_text(text)

        aria_labelledby = str(element.get("aria-labelledby") or "")
        if aria_labelledby:
            parts = []
            for labelled_id in aria_labelledby.split():
                labelled = soup.find(id=labelled_id)
                if isinstance(labelled, Tag):
                    parts.append(labelled.get_text(" ", strip=True))
            if parts:
                return self._clean_text(" ".join(parts))

        return ""

    def _radio_group_label(self, element: Tag) -> str:
        fieldset = element.find_parent("fieldset")
        if isinstance(fieldset, Tag):
            legend = fieldset.find("legend")
            if isinstance(legend, Tag):
                return self._clean_text(legend.get_text(" ", strip=True))
        return ""

    def _context_for_element(self, element: Tag) -> str:
        parent = element.find_parent(["fieldset", "div", "section", "li"])
        if not isinstance(parent, Tag):
            return ""
        text = parent.get_text(" ", strip=True)
        return self._clean_text(text[:280])

    def _selector_for_element(self, element: Tag) -> str:
        element_id = str(element.get("id") or "")
        if element_id:
            return f"#{self._css_escape(element_id)}"
        name = str(element.get("name") or "")
        if name:
            return f'{element.name}[name="{name}"]'
        return str(element.name or "")

    def _element_field_id(self, element: Tag, index: int) -> str:
        return str(element.get("id") or element.get("name") or f"{element.name}_{index}")

    def _field_text(self, field: AutofillField) -> str:
        direct = " ".join(
            [
                field.label,
                field.name,
                field.id_attr,
                field.placeholder,
                field.aria_label,
            ]
        )
        if self._normalize(direct):
            return direct
        return field.context

    def _is_non_application_control(self, element: Tag) -> bool:
        input_type = str(element.get("type", "")).lower()
        return input_type in {"hidden", "submit", "button", "reset", "image"}

    @classmethod
    def _contains_any(cls, normalized: str, terms: tuple[str, ...]) -> bool:
        return any(cls._normalize(term) in normalized for term in terms)

    @staticmethod
    def _has_word(normalized: str, word: str) -> bool:
        return re.search(rf"\b{re.escape(word)}\b", normalized) is not None

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", unescape(value or "")).strip()

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (value or "").lower())).strip()

    @staticmethod
    def _css_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace(":", "\\:")

    @staticmethod
    def _load_json(path_str: str) -> dict[str, Any]:
        return json.loads(Path(path_str).read_text(encoding="utf-8"))

    @staticmethod
    def _yes_no(value: object) -> str:
        if value is True:
            return "Yes"
        if value is False:
            return "No"
        return ""

    @staticmethod
    def _normalize_url(value: str) -> str:
        if not value:
            return ""
        parsed = urlparse(value.strip())
        query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            path=parsed.path.rstrip("/"),
            query=query,
            fragment="",
        )
        return urlunparse(normalized)

    @classmethod
    def _meaningful_tokens(cls, value: str) -> list[str]:
        stop_words = {
            "and",
            "the",
            "for",
            "with",
            "engineer",
            "developer",
            "analyst",
            "scientist",
            "junior",
            "senior",
            "remote",
            "job",
            "role",
        }
        return [
            token
            for token in cls._normalize(value).split()
            if len(token) >= 3 and token not in stop_words
        ]
