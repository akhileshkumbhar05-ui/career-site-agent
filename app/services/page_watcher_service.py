"""Page watcher ("third eye") service.

Looks at one browser page at a time and answers three questions, ATS-agnostic:
  1. What kind of page is this? (job description, application form, both, confirmation, other)
  2. If it is a job posting, what is the job? (structured JD understanding)
  3. Given the page's form fields, what can we safely suggest filling? (suggest, never submit)

Claude is the primary brain. The deterministic ATSAutofillService matcher provides a
safe baseline and an offline fallback, and always enforces the sensitive-field guardrails
(EEO, citizenship/clearance, salary, SSN/DOB, signatures, submit are never auto-filled).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

try:
    import anthropic
except ImportError:  # pragma: no cover - optional runtime dependency
    anthropic = None

from app.schemas.ats_autofill import (
    AutofillField,
    AutofillMatch,
    WatcherFieldSuggestion,
    WatcherJD,
    WatcherObserveRequest,
    WatcherObserveResponse,
)
from app.services.ats_autofill_service import ATSAutofillService
from app.services.autofill_context_service import AutofillContextService

logger = logging.getLogger(__name__)

CONFIRMATION_MARKERS = (
    "application received",
    "thank you for applying",
    "thanks for applying",
    "your application has been submitted",
    "application submitted",
    "we have received your application",
)

_NON_TEXT_INPUT_TYPES = {"select", "radio_group", "file", "checkbox", "hidden", "submit", "button"}

_WATCHER_SYSTEM = """
You are the page-awareness brain ("third eye") for a job-application assistant.
You see ONE web page at a time and must:
  1. Classify the page.
  2. If it is a job posting, extract the job into structured fields.
  3. Propose answers for the application form fields using ONLY the applicant profile below
     and the job description visible on the page.

Hard rules:
- Never invent facts that are not in the applicant profile.
- Never propose a value for sensitive fields: EEO / demographic (gender, race, veteran, disability),
  citizenship or security clearance, salary or compensation, SSN or date of birth, password, or signature.
  Mark those with "sensitive": true and an empty "value".
- Prefer short, honest, profile-grounded answers. For free-text questions like "why are you interested",
  keep it to one or two sentences grounded in the job description and the profile.
- Return ONLY valid JSON. No markdown fences, no preamble.

APPLICANT PROFILE:
{profile}
""".strip()

_WATCHER_USER = """
PAGE URL: {url}
PAGE TITLE: {title}

FORM FIELDS (id | type | label | options):
{fields}

PAGE TEXT (truncated):
{page_text}

Return JSON with exactly this shape:
{{
  "page_type": "job_description" | "application_form" | "both" | "confirmation" | "other",
  "page_type_confidence": 0.0,
  "jd": {{
    "company": "",
    "role": "",
    "location": "",
    "seniority": "",
    "sponsorship_note": "",
    "key_requirements": [],
    "summary": ""
  }},
  "field_answers": [
    {{"field_id": "", "value": "", "confidence": 0.0, "sensitive": false, "reason": ""}}
  ]
}}

- Use "both" when the page shows the job description and an application form together.
- Use "confirmation" only for a post-submit acknowledgement page.
- Fill "jd" only when the page contains an actual job description; otherwise leave its fields empty.
- "sponsorship_note": if the posting says it does or does not sponsor work visas (H-1B, OPT, STEM OPT, TN), say so briefly.
- In "field_answers", only include fields you can answer from the profile (name, email, phone, location,
  links, work authorization, relocation) or a short JD-specific free-text answer. Use the exact field_id given.
- Leave every sensitive field with "sensitive": true and an empty "value".
""".strip()


class PageWatcherService:
    def __init__(
        self,
        *,
        autofill: ATSAutofillService,
        api_key: str = "",
        model: str = "claude-sonnet-4-6",
        profile_path: str = "data/application_profile.json",
    ) -> None:
        self.autofill = autofill
        self.model = model
        self.profile_path = Path(profile_path)
        self._client = None
        self._profile: dict | None = None
        if api_key and anthropic is not None:
            try:
                self._client = anthropic.Anthropic(api_key=api_key)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Watcher Claude client init failed: %s", exc)

    def observe(self, payload: WatcherObserveRequest) -> WatcherObserveResponse:
        page_text = (payload.page_text or "")[: payload.max_page_text_chars]
        fields = list(payload.form_fields)

        matched_context = self.autofill.load_context_for_url(payload.url)
        if matched_context.source == "matched_apply_plan":
            apply_plan = matched_context.apply_plan
        else:
            apply_plan = self.autofill.build_profile_apply_plan(
                payload.url,
                {"company": payload.company, "title": payload.role, "discovered_url": payload.url},
            )
        heuristic_plan = self.autofill.build_plan(fields, apply_plan, source_url=payload.url)
        suggestions = [self._suggestion_from_match(match, source="heuristic") for match in heuristic_plan.matches]

        identity = AutofillContextService._infer_page_identity(payload.page_title, payload.url, page_text)
        has_jd = AutofillContextService._has_job_description_signal(page_text)
        fillable_field_count = sum(
            1 for field in fields if (field.input_type or field.tag) not in {"hidden", "submit", "button", "search"}
        )

        llm_result = None
        if payload.use_llm and self._client is not None and (has_jd or fillable_field_count):
            llm_result = self._call_claude(payload, page_text, fields)

        if llm_result:
            engine = "claude"
            page_type = str(llm_result.get("page_type") or "") or self._heuristic_page_type(
                has_jd, fillable_field_count, page_text
            )
            confidence = self._safe_float(llm_result.get("page_type_confidence"), 0.8)
            jd = self._jd_from_llm(llm_result.get("jd") or {}, identity, page_type)
            suggestions = self._merge_llm_answers(suggestions, llm_result.get("field_answers") or [], fields)
        else:
            engine = "heuristic"
            page_type = self._heuristic_page_type(has_jd, fillable_field_count, page_text)
            confidence = 0.55
            jd = self._heuristic_jd(identity, has_jd, page_text, page_type)

        fillable = sum(1 for item in suggestions if item.action in {"fill_text", "select_option", "choose_radio"})
        manual = sum(1 for item in suggestions if item.action in {"manual_review", "manual_upload"})
        sensitive = sum(1 for item in suggestions if item.sensitive)

        return WatcherObserveResponse(
            page_type=page_type,
            page_type_confidence=confidence,
            engine=engine,
            jd=jd,
            field_suggestions=suggestions,
            fillable_count=fillable,
            manual_count=manual,
            sensitive_count=sensitive,
            message=self._message(page_type, engine, fillable, sensitive),
        )

    # ----- suggestions -----

    @staticmethod
    def _suggestion_from_match(match: AutofillMatch, *, source: str) -> WatcherFieldSuggestion:
        reason = (match.reason or "").lower()
        sensitive = match.action == "skip_sensitive" or (
            match.action == "manual_review"
            and any(term in reason for term in ("citizenship", "clearance", "compensation", "salary"))
        )
        return WatcherFieldSuggestion(
            field_id=match.field.field_id,
            selector=match.field.selector,
            label=match.field.label or match.field.name or match.field.placeholder,
            action=match.action,
            value=match.answer_value,
            target_option=match.target_option,
            confidence=match.confidence,
            reason=match.reason,
            sensitive=sensitive,
            source=source,
        )

    def _merge_llm_answers(
        self,
        suggestions: list[WatcherFieldSuggestion],
        llm_answers: list,
        fields: list[AutofillField],
    ) -> list[WatcherFieldSuggestion]:
        by_id = {item.field_id: item for item in suggestions}
        field_by_id = {field.field_id: field for field in fields}

        for answer in llm_answers:
            if not isinstance(answer, dict):
                continue
            field_id = str(answer.get("field_id") or "")
            suggestion = by_id.get(field_id)
            field = field_by_id.get(field_id)
            if not suggestion or not field:
                continue
            # Hard guardrail: a heuristic-blocked sensitive field stays blocked no matter what the LLM says.
            if suggestion.action == "skip_sensitive" or suggestion.sensitive:
                continue
            if answer.get("sensitive"):
                continue
            value = str(answer.get("value") or "").strip()
            if not value:
                continue
            # Only upgrade ambiguous text-like fields; selects/radios/files stay with the deterministic matcher.
            if suggestion.action in {"manual_review", "skip_unknown"} and (field.input_type or field.tag) not in _NON_TEXT_INPUT_TYPES:
                suggestion.action = "fill_text"
                suggestion.value = value
                suggestion.confidence = self._safe_float(answer.get("confidence"), 0.7)
                suggestion.reason = str(answer.get("reason") or "Claude proposed this from your profile and the job description.")
                suggestion.source = "claude"

        return list(by_id.values())

    # ----- page-type + JD -----

    @staticmethod
    def _heuristic_page_type(has_jd: bool, fillable_field_count: int, page_text: str) -> str:
        lowered = page_text.lower()
        if any(marker in lowered for marker in CONFIRMATION_MARKERS):
            return "confirmation"
        many_fields = fillable_field_count >= 4
        if has_jd and many_fields:
            return "both"
        if many_fields:
            return "application_form"
        if has_jd:
            return "job_description"
        return "other"

    @staticmethod
    def _heuristic_jd(identity: dict, has_jd: bool, page_text: str, page_type: str) -> WatcherJD | None:
        if page_type not in {"job_description", "both"} and not has_jd:
            return None
        if not identity.get("role") and not has_jd:
            return None
        return WatcherJD(
            company=identity.get("company", ""),
            role=identity.get("role", ""),
            location=identity.get("location", ""),
            summary=page_text[:280].strip(),
        )

    def _jd_from_llm(self, jd: dict, identity: dict, page_type: str) -> WatcherJD | None:
        has_payload = any(str(jd.get(key) or "").strip() for key in ("company", "role", "summary"))
        if not has_payload and page_type not in {"job_description", "both"}:
            return None
        return WatcherJD(
            company=str(jd.get("company") or identity.get("company") or ""),
            role=str(jd.get("role") or identity.get("role") or ""),
            location=str(jd.get("location") or identity.get("location") or ""),
            seniority=str(jd.get("seniority") or ""),
            sponsorship_note=str(jd.get("sponsorship_note") or ""),
            key_requirements=[str(item) for item in (jd.get("key_requirements") or []) if str(item).strip()][:8],
            summary=str(jd.get("summary") or ""),
        )

    @staticmethod
    def _message(page_type: str, engine: str, fillable: int, sensitive: int) -> str:
        label = {
            "job_description": "This looks like a job description.",
            "application_form": "This looks like an application form.",
            "both": "This page shows the job description and an application form.",
            "confirmation": "This looks like an application confirmation page.",
            "other": "This does not look like a job or application page.",
        }.get(page_type, "Page observed.")
        if page_type in {"application_form", "both"}:
            label += f" {fillable} safe field(s) ready to suggest; {sensitive} left for you."
        return f"{label} (via {engine})"

    # ----- Claude -----

    def _call_claude(self, payload: WatcherObserveRequest, page_text: str, fields: list[AutofillField]) -> dict | None:
        field_lines = []
        for field in fields[:40]:
            options = f" | options: {', '.join(field.options[:8])}" if field.options else ""
            label = field.label or field.name or field.placeholder or field.aria_label or "(unlabeled)"
            field_lines.append(f"- {field.field_id} | {field.input_type or field.tag} | {label}{options}")
        fields_block = "\n".join(field_lines) or "(no form fields detected)"

        system = _WATCHER_SYSTEM.format(profile=json.dumps(self._load_profile(), indent=2))
        user = _WATCHER_USER.format(
            url=payload.url or "(unknown)",
            title=payload.page_title or "(none)",
            fields=fields_block,
            page_text=page_text[:6000],
        )
        try:
            request = {
                "model": self.model,
                "max_tokens": 1500,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
            if self.model == "claude-sonnet-5":
                request["thinking"] = {"type": "disabled"}
            message = self._client.messages.create(**request)
            text_block = next(
                (block for block in message.content if getattr(block, "type", "") == "text"),
                None,
            )
            if text_block is None:
                logger.warning("Watcher Claude response did not include a text block.")
                return None
            raw = text_block.text.strip()
            if raw.startswith("```"):
                raw = "\n".join(line for line in raw.splitlines() if not line.strip().startswith("```")).strip()
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Watcher Claude JSON parse failed: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Watcher Claude call failed: %s", exc)
            return None

    def _load_profile(self) -> dict:
        if self._profile is None:
            try:
                self._profile = json.loads(self.profile_path.read_text(encoding="utf-8"))
            except Exception:
                self._profile = {}
        return self._profile

    @staticmethod
    def _safe_float(value: object, fallback: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(1.0, number))
