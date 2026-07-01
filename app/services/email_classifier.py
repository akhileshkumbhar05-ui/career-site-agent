from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.services.llm_service import LLMService

ROOT_DIR = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT_DIR / "data" / "email_status_rules.json"


def classify_email(
    subject: str,
    body: str,
    sender_email: str = "",
    sender_name: str = "",
) -> dict[str, Any]:
    rules_config = _load_rules()
    allowed_statuses = set(rules_config.get("status_options", []))
    full_text = f"{subject}\n\n{body}"
    company_name = _extract_company(subject, sender_email, sender_name, rules_config)

    candidates = _matching_rule_candidates(rules_config, subject, body, full_text, sender_email, allowed_statuses)
    if candidates:
        deterministic = _select_best_candidate(candidates)
        llm_result = _maybe_llm_classify(
            rules_config=rules_config,
            subject=subject,
            body=body,
            sender_email=sender_email,
            sender_name=sender_name,
            company_name=company_name,
            deterministic=deterministic,
            candidates=candidates,
            is_job_related=True,
            allowed_statuses=allowed_statuses,
        )
        if llm_result:
            return llm_result
        return _candidate_to_result(company_name, deterministic)

    is_job_related = _match_any(full_text, rules_config.get("review_if_unmatched_patterns", []))
    if is_job_related:
        deterministic = _result(
            company=company_name,
            email_type="unknown",
            status="",
            confidence=0.30,
            reasoning="Job-related signal found, but no status rule matched; manual review needed",
            requires_review=True,
            is_job_related=True,
            matched_rule="unmatched_job_related",
            matched_pattern="",
        )
        llm_result = _maybe_llm_classify(
            rules_config=rules_config,
            subject=subject,
            body=body,
            sender_email=sender_email,
            sender_name=sender_name,
            company_name=company_name,
            deterministic=deterministic,
            candidates=[],
            is_job_related=True,
            allowed_statuses=allowed_statuses,
        )
        if llm_result:
            return llm_result
        return _result(
            company=company_name,
            email_type="unknown",
            status="",
            confidence=0.30,
            reasoning="Job-related signal found, but no status rule matched; manual review needed",
            requires_review=True,
            is_job_related=True,
            matched_rule="unmatched_job_related",
            matched_pattern="",
        )

    return _result(
        company=company_name,
        email_type="ignore",
        status="",
        confidence=0.90,
        reasoning="No job-application status signal found; ignored",
        requires_review=False,
        is_job_related=False,
        matched_rule="unmatched_not_job_related",
        matched_pattern="",
    )


def _load_rules() -> dict[str, Any]:
    with RULES_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _matching_rule_candidates(
    rules_config: dict[str, Any],
    subject: str,
    body: str,
    full_text: str,
    sender_email: str,
    allowed_statuses: set[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, rule in enumerate(rules_config.get("rules", [])):
        match = _match_rule(rule, subject, body, full_text, sender_email)
        if not match:
            continue

        status = str(rule.get("status") or "")
        if status and status not in allowed_statuses:
            status = ""

        email_type = str(rule.get("email_type") or rule.get("id") or "unknown")
        candidates.append(
            {
                "company": "",
                "email_type": email_type,
                "status": status,
                "confidence": float(rule.get("confidence") or 0.0),
                "reasoning": _build_reasoning(str(rule.get("reason") or ""), match),
                "requires_review": bool(rule.get("requires_review", False)),
                "is_job_related": bool(rule.get("is_job_related", True)),
                "matched_rule": str(rule.get("id") or ""),
                "matched_pattern": match["pattern"],
                "priority": int(rule.get("priority") or _default_rule_priority(rule, index)),
                "rule_index": index,
            }
        )
    return candidates


def _select_best_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        candidates,
        key=lambda item: (
            item["priority"],
            1 if item["status"] else 0,
            item["confidence"],
            -item["rule_index"],
        ),
        reverse=True,
    )[0]


def _candidate_to_result(company_name: str, candidate: dict[str, Any]) -> dict[str, Any]:
    return _result(
        company=company_name,
        email_type=candidate["email_type"],
        status=candidate["status"],
        confidence=candidate["confidence"],
        reasoning=candidate["reasoning"],
        requires_review=candidate["requires_review"],
        is_job_related=candidate["is_job_related"],
        matched_rule=candidate["matched_rule"],
        matched_pattern=candidate["matched_pattern"],
    )


def _default_rule_priority(rule: dict[str, Any], index: int) -> int:
    email_type = str(rule.get("email_type") or rule.get("id") or "").lower()
    status = str(rule.get("status") or "")
    is_job_related = bool(rule.get("is_job_related", True))

    if not is_job_related:
        return 100
    if email_type == "offer":
        return 95
    if "rejection" in email_type:
        return 90
    if status and "Interview Call" in status:
        return 86
    if email_type == "cleared_automated":
        return 82
    if email_type == "job_digest":
        return 70
    if email_type == "acknowledgment":
        return 20
    return max(10, 60 - index)


def _match_rule(
    rule: dict[str, Any],
    subject: str,
    body: str,
    full_text: str,
    sender_email: str,
) -> dict[str, str] | None:
    field_patterns = [
        ("sender", sender_email, rule.get("sender_patterns", [])),
        ("subject", subject, rule.get("subject_patterns", [])),
        ("body", body, rule.get("body_patterns", [])),
        ("text", full_text, rule.get("patterns", [])),
    ]

    for field_name, text, patterns in field_patterns:
        match = _first_match(text, patterns)
        if match:
            return {"field": field_name, "pattern": match}

    return None


def _first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        if re.search(pattern, text or "", flags=re.IGNORECASE | re.DOTALL):
            return pattern
    return ""


def _match_any(text: str, patterns: list[str]) -> bool:
    return bool(_first_match(text, patterns))


def _maybe_llm_classify(
    *,
    rules_config: dict[str, Any],
    subject: str,
    body: str,
    sender_email: str,
    sender_name: str,
    company_name: str,
    deterministic: dict[str, Any],
    candidates: list[dict[str, Any]],
    is_job_related: bool,
    allowed_statuses: set[str],
) -> dict[str, Any]:
    if not _should_use_llm(deterministic, candidates, is_job_related):
        return {}

    llm = LLMService()
    if not llm.is_available():
        return {}

    prompt = json.dumps(
        {
            "task": "Classify this job application email status update.",
            "allowed_statuses": sorted(allowed_statuses),
            "email": {
                "subject": subject[:500],
                "body": body[:4000],
                "sender_email": sender_email,
                "sender_name": sender_name,
            },
            "deterministic_candidate": _llm_candidate_excerpt(deterministic),
            "all_rule_candidates": [_llm_candidate_excerpt(candidate) for candidate in candidates[:6]],
            "rules": {
                "acknowledgment_means_no_status_update": True,
                "rejection_language_overrides_acknowledgment_language": True,
                "job_digests_or_recommendations_are_not_application_status_updates": True,
            },
            "return_schema": {
                "email_type": "rejection | acknowledgment | screening_interview | technical_interview | hr_interview | offer | job_digest | ignore | unknown",
                "new_status": "one allowed status or empty string",
                "confidence": "number 0.0 to 1.0",
                "requires_review": "boolean",
                "is_job_related": "boolean",
                "reasoning": "one short sentence",
            },
        },
        indent=2,
    )
    system = (
        "You classify job application emails. Return only valid JSON. "
        "Prioritize actual outcome/status language over polite acknowledgments. "
        "Do not invent company names or statuses."
    )
    raw = llm.generate_json(prompt, system=system)
    if not raw:
        return {}

    status = str(raw.get("new_status") or raw.get("status") or "").strip()
    if status and status not in allowed_statuses:
        status = ""

    email_type = str(raw.get("email_type") or deterministic.get("email_type") or "unknown")
    status, email_type = _reconcile_llm_status(
        proposed_status=status,
        proposed_email_type=email_type,
        deterministic=deterministic,
        candidates=candidates,
    )
    confidence = _coerce_confidence(raw.get("confidence"), float(deterministic.get("confidence") or 0.0))
    matched_rule = f"llm_adjudicated:{deterministic.get('matched_rule', '')}"
    reasoning = str(raw.get("reasoning") or "Local LLM adjudicated ambiguous job email classification")

    return _result(
        company=company_name,
        email_type=email_type,
        status=status,
        confidence=confidence,
        reasoning=reasoning,
        requires_review=bool(raw.get("requires_review", deterministic.get("requires_review", False))),
        is_job_related=bool(raw.get("is_job_related", deterministic.get("is_job_related", True))),
        matched_rule=matched_rule,
        matched_pattern=str(deterministic.get("matched_pattern") or ""),
    )


def _should_use_llm(deterministic: dict[str, Any], candidates: list[dict[str, Any]], is_job_related: bool) -> bool:
    if not is_job_related:
        return False

    email_type = str(deterministic.get("email_type") or "")
    confidence = float(deterministic.get("confidence") or 0.0)
    status = str(deterministic.get("status") or deterministic.get("new_status") or "")
    if status and confidence >= 0.85 and deterministic.get("requires_review") is not True:
        return False

    has_status_conflict = any(candidate.get("status") for candidate in candidates) and any(
        not candidate.get("status") for candidate in candidates
    )

    return (
        deterministic.get("requires_review") is True
        or email_type == "unknown"
        or confidence < 0.70
        or has_status_conflict
    )


def _reconcile_llm_status(
    *,
    proposed_status: str,
    proposed_email_type: str,
    deterministic: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> tuple[str, str]:
    email_type = proposed_email_type
    status = proposed_status
    deterministic_status = str(deterministic.get("status") or deterministic.get("new_status") or "")

    if email_type in {"acknowledgment", "job_digest", "ignore"}:
        return "", email_type

    if deterministic_status and status != deterministic_status:
        supported_statuses = {
            str(candidate.get("status") or candidate.get("new_status") or "")
            for candidate in candidates
            if candidate.get("status") or candidate.get("new_status")
        }
        if status not in supported_statuses:
            status = deterministic_status
            email_type = str(deterministic.get("email_type") or email_type)

    return status, email_type


def _llm_candidate_excerpt(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "email_type": candidate.get("email_type"),
        "new_status": candidate.get("status") or candidate.get("new_status") or "",
        "confidence": candidate.get("confidence"),
        "requires_review": candidate.get("requires_review"),
        "matched_rule": candidate.get("matched_rule"),
        "matched_pattern": candidate.get("matched_pattern"),
        "reasoning": candidate.get("reasoning"),
    }


def _coerce_confidence(value: Any, default: float) -> float:
    try:
        output = float(value)
    except (TypeError, ValueError):
        output = default
    return max(0.0, min(1.0, output))


def _extract_company(
    subject: str,
    sender_email: str,
    sender_name: str,
    rules_config: dict[str, Any],
) -> str:
    for pattern in rules_config.get("company_subject_patterns", []):
        match = re.search(pattern, subject or "", flags=re.IGNORECASE)
        if match and match.groupdict().get("company"):
            return _clean_company(match.group("company"))

    domain_company = _extract_company_from_sender(sender_email, rules_config)
    if domain_company:
        return domain_company

    if sender_name:
        cleaned = _clean_company(sender_name)
        if cleaned and not _looks_generic_sender_name(cleaned):
            return cleaned

    return ""


def _extract_company_from_sender(sender_email: str, rules_config: dict[str, Any]) -> str:
    if not sender_email or "@" not in sender_email:
        return ""

    domain = sender_email.split("@", 1)[1].lower().strip()
    generic_domains = {str(item).lower() for item in rules_config.get("generic_sender_domains", [])}
    if domain in generic_domains or any(domain.endswith(f".{item}") for item in generic_domains):
        return ""

    company_slug = domain.split(".")[0]
    return _clean_company(company_slug.replace("-", " "))


def _looks_generic_sender_name(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "", value.lower())
    generic_tokens = {
        "noreply",
        "donotreply",
        "jobs",
        "recruiting",
        "talent",
        "workday",
        "workflow",
        "greenhouse",
        "lever",
        "brassring",
        "linkedin",
        "glassdoorjobs",
    }
    return normalized in generic_tokens or normalized.endswith("jobs")


def _clean_company(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" -:|,.\t\r\n")
    cleaned = re.sub(r"\b(no.?reply|do.?not.?reply|jobs|careers|recruiting|talent)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:|,.\t\r\n")
    if cleaned and cleaned == cleaned.lower():
        cleaned = cleaned.title()
    return cleaned[:80]


def _build_reasoning(reason: str, match: dict[str, str]) -> str:
    if not match.get("pattern"):
        return reason
    return f"{reason}; matched {match['field']} rule `{match['pattern']}`"


def _result(
    company: str,
    email_type: str,
    status: str,
    confidence: float,
    reasoning: str,
    requires_review: bool,
    is_job_related: bool,
    matched_rule: str,
    matched_pattern: str,
) -> dict[str, Any]:
    return {
        "company_name": company,
        "email_type": email_type,
        "new_status": status,
        "confidence": confidence,
        "reasoning": reasoning,
        "requires_review": requires_review,
        "is_job_related": is_job_related,
        "matched_rule": matched_rule,
        "matched_pattern": matched_pattern,
    }
