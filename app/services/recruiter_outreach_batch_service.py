from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

try:
    import anthropic
except ImportError:  # pragma: no cover - optional runtime dependency
    anthropic = None


logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You draft concise LinkedIn connection-request notes for Akhilesh Kumbhar after he has
manually submitted a job application.

Hard rules:
- Use only the supplied candidate evidence and job context. Never invent experience,
  metrics, relationships, recruiter names, or company knowledge.
- Each note must be no more than 280 characters.
- Say that the application was submitted. Mention one relevant, grounded strength.
- Be warm and specific, not needy. Do not ask for a referral or imply prior contact.
- Do not include a subject line, markdown, placeholders, or a signature block.
- Return only valid JSON in the requested shape.
""".strip()


class RecruiterOutreachBatchService:
    def __init__(
        self,
        *,
        api_key: str = "",
        model: str = "claude-sonnet-5",
        resume_path: str | Path = "data/master_resume/master_resume.json",
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.resume_path = Path(resume_path)
        self._resume: dict[str, Any] | None = None
        self._client = client
        if self._client is None and api_key and anthropic is not None:
            try:
                self._client = anthropic.Anthropic(api_key=api_key)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Recruiter outreach Claude client init failed: %s", exc)

    def cache_key(self, job: dict[str, Any]) -> str:
        stable = {
            "company": str(job.get("company") or "").strip(),
            "role": str(job.get("role") or "").strip(),
            "jd_text": str(job.get("jd_text") or "").strip(),
            "fit_strengths": list(job.get("fit_strengths") or []),
            "model": self.model,
            "candidate": self._candidate_evidence(),
        }
        encoded = json.dumps(stable, sort_keys=True, ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def draft_batch(self, jobs: list[dict[str, Any]], *, use_llm: bool = True) -> dict[str, Any]:
        if not jobs:
            return {
                "notes": {},
                "engine": "deterministic_fallback",
                "model": "",
                "llm_usage": {},
                "claude_call_consumed": False,
            }

        if use_llm and self._client is not None:
            result = self._call_claude(jobs)
            notes = self._validated_notes(result.get("notes"), jobs) if result else {}
            if len(notes) == len(jobs):
                return {
                    "notes": notes,
                    "engine": "claude",
                    "model": self.model,
                    "llm_usage": result.get("llm_usage") or {},
                    "claude_call_consumed": True,
                }
            fallback_usage = result.get("llm_usage") if result else {}
            return {
                "notes": {str(job["loop_id"]): self._fallback_note(job) for job in jobs},
                "engine": "deterministic_fallback",
                "model": self.model,
                "llm_usage": fallback_usage or {},
                "claude_call_consumed": True,
            }

        return {
            "notes": {str(job["loop_id"]): self._fallback_note(job) for job in jobs},
            "engine": "deterministic_fallback",
            "model": "",
            "llm_usage": {},
            "claude_call_consumed": False,
        }

    def _call_claude(self, jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
        payload = {
            "candidate_evidence": self._candidate_evidence(),
            "jobs": [
                {
                    "loop_id": str(job["loop_id"]),
                    "company": str(job.get("company") or ""),
                    "role": str(job.get("role") or ""),
                    "fit_strengths": list(job.get("fit_strengths") or [])[:3],
                    "jd_excerpt": str(job.get("jd_text") or "")[:900],
                }
                for job in jobs
            ],
            "response_shape": {
                "notes": [
                    {"loop_id": "exact loop_id from input", "note": "connection note, 280 characters max"}
                ]
            },
        }
        try:
            request: dict[str, Any] = {
                "model": self.model,
                "max_tokens": 2200,
                "system": [
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=True)}],
            }
            if self.model == "claude-sonnet-5":
                request["thinking"] = {"type": "disabled"}
            message = self._client.messages.create(**request)
            text_block = next(
                (block for block in message.content if getattr(block, "type", "") == "text"),
                None,
            )
            if text_block is None:
                return None
            raw = text_block.text.strip()
            if raw.startswith("```"):
                raw = "\n".join(
                    line for line in raw.splitlines() if not line.strip().startswith("```")
                ).strip()
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return None
            usage = getattr(message, "usage", None)
            parsed["llm_usage"] = {
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
                "cache_creation_input_tokens": int(
                    getattr(usage, "cache_creation_input_tokens", 0) or 0
                ),
                "cache_read_input_tokens": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            }
            return parsed
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("Recruiter outreach Claude response was invalid: %s", exc)
            return None
        except Exception as exc:  # pragma: no cover - provider/network failure
            logger.warning("Recruiter outreach Claude call failed: %s", exc)
            return None

    @staticmethod
    def _validated_notes(raw_notes: Any, jobs: list[dict[str, Any]]) -> dict[str, str]:
        if not isinstance(raw_notes, list):
            return {}
        expected = {str(job["loop_id"]) for job in jobs}
        notes: dict[str, str] = {}
        for raw in raw_notes:
            if not isinstance(raw, dict):
                continue
            loop_id = str(raw.get("loop_id") or "")
            note = " ".join(str(raw.get("note") or "").split())
            if loop_id in expected and 20 <= len(note) <= 280:
                notes[loop_id] = note
        return notes

    def _candidate_evidence(self) -> dict[str, Any]:
        resume = self._load_resume()
        candidate = resume.get("candidate") or {}
        experience = resume.get("experience") or []
        projects = resume.get("projects") or []
        publications = resume.get("publications") or resume.get("research") or []
        return {
            "headline": str(candidate.get("headline") or "Data Scientist and AI Engineer"),
            "summary": str(candidate.get("base_summary") or "")[:900],
            "experience_evidence": [
                bullet
                for entry in experience[:2]
                for bullet in (entry.get("bullets") or [])[:2]
            ],
            "project_evidence": [
                bullet
                for entry in projects[:3]
                for bullet in (entry.get("bullets") or [])[:1]
            ],
            "research_evidence": [
                bullet
                for entry in publications[:2]
                for bullet in (entry.get("bullets") or [])[:1]
            ],
        }

    def _load_resume(self) -> dict[str, Any]:
        if self._resume is None:
            try:
                self._resume = json.loads(self.resume_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._resume = {}
        return self._resume

    @staticmethod
    def _fallback_note(job: dict[str, Any]) -> str:
        role = RecruiterOutreachBatchService._compact_label(
            str(job.get("role") or "the role"),
            max_chars=72,
        )
        company = RecruiterOutreachBatchService._compact_label(
            str(job.get("company") or "your company"),
            max_chars=48,
        )
        role_key = role.casefold()
        if any(term in role_key for term in ("analyst", "business intelligence", "reporting")):
            strength = "Python, SQL, Power BI, and operational analytics"
        elif any(term in role_key for term in ("machine learning", "data scientist", "ai")):
            strength = "production ML, recommender systems, and applied AI"
        else:
            strength = "Python, data systems, and workflow automation"
        note = (
            f"Hi, I recently applied for the {role} role at {company}. "
            f"My background in {strength} aligns well with the work, and I would value connecting with your team."
        )
        return note

    @staticmethod
    def _compact_label(value: str, *, max_chars: int) -> str:
        normalized = " ".join(value.split())
        if len(normalized) <= max_chars:
            return normalized
        shortened = normalized[: max_chars + 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
        return shortened or normalized[:max_chars].rstrip(" ,.;:-")
