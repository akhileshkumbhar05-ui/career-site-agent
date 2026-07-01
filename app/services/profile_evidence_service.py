from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class ProfileEvidenceService:
    """Loads safe resume-tailoring evidence from the local Profile folder.

    The Profile folder can contain personal documents and credentials. This
    service only returns redacted text intended for LLM prompts or metadata.
    """

    DEFAULT_PROFILE_DIR = Path("Profile")
    SUMMARY_NAMES = ("EREV Summary.txt", "ICTCS2022 Summary.txt")
    TEXT_SUFFIXES = {".txt", ".md"}
    SUPPORTED_ARTIFACT_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}

    SECRET_PATTERNS = (
        re.compile(r"github_pat_[A-Za-z0-9_]+"),
        re.compile(r"gh[pousr]_[A-Za-z0-9_]+"),
        re.compile(r"(?i)(api[_ -]?key|access[_ -]?token|token|password|secret)\s*[:=]\s*\S+"),
        re.compile(r"https://[^\s]*(?:access_token|auth|github_pat|gh[pousr]_|oauth|token)[^\s]*", re.IGNORECASE),
    )

    def __init__(self, profile_dir: str | Path = DEFAULT_PROFILE_DIR) -> None:
        self.profile_dir = Path(profile_dir)

    def build_prompt_context(self, *, max_chars: int = 22000) -> dict[str, Any]:
        if not self.profile_dir.exists():
            return {
                "available": False,
                "profile_dir": str(self.profile_dir),
                "instructions": "",
                "evidence_summaries": [],
                "artifact_index": [],
            }

        instructions = self._read_text("Instructions.txt", max_chars=7000)
        summaries = []
        for name in self.SUMMARY_NAMES:
            text = self._read_text(name, max_chars=6500)
            if text:
                summaries.append({"source": name, "text": text})

        context: dict[str, Any] = {
            "available": True,
            "profile_dir": str(self.profile_dir),
            "instructions": instructions,
            "evidence_summaries": summaries,
            "artifact_index": self.artifact_index(),
            "safety_note": (
                "Use this evidence only when the JD has a clear connection. "
                "Never expose, copy, or infer credentials/access links."
            ),
        }
        return self._truncate_context(context, max_chars=max_chars)

    def artifact_index(self) -> list[dict[str, str]]:
        if not self.profile_dir.exists():
            return []

        artifacts = []
        for path in sorted(self.profile_dir.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_file() or path.suffix.lower() not in self.SUPPORTED_ARTIFACT_SUFFIXES:
                continue
            artifacts.append(
                {
                    "name": path.name,
                    "type": path.suffix.lower().lstrip("."),
                    "safe_path": str(path),
                    "usage_hint": self._usage_hint(path.name),
                }
            )
        return artifacts

    def base_resume_pdf(self) -> str:
        if not self.profile_dir.exists():
            return ""
        matches = sorted(self.profile_dir.glob("*Resume*.pdf"))
        return str(matches[0].resolve()) if matches else ""

    def _read_text(self, name: str, *, max_chars: int) -> str:
        path = self.profile_dir / name
        if not path.exists() or path.suffix.lower() not in self.TEXT_SUFFIXES:
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        return self._sanitize(text)[:max_chars].strip()

    @classmethod
    def _sanitize(cls, text: str) -> str:
        sanitized_lines = []
        for line in (text or "").splitlines():
            if cls._looks_like_secret_line(line):
                sanitized_lines.append(cls._redact_line(line))
                continue
            sanitized = line
            for pattern in cls.SECRET_PATTERNS:
                sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
            sanitized_lines.append(sanitized)
        return "\n".join(sanitized_lines)

    @staticmethod
    def _looks_like_secret_line(line: str) -> bool:
        lowered = line.lower()
        return any(term in lowered for term in ("access link", "access token", "api key", "password", "secret"))

    @staticmethod
    def _redact_line(line: str) -> str:
        if ":" in line:
            key = line.split(":", 1)[0].strip()
            return f"{key}: [REDACTED_SECRET]"
        return "[REDACTED_SECRET]"

    @staticmethod
    def _usage_hint(name: str) -> str:
        lowered = name.lower()
        if "bioinformatics" in lowered or "healthcare" in lowered:
            return "Use for healthcare, biotech, bioinformatics, diagnostics, or research roles."
        if "robotics" in lowered:
            return "Use for robotics, computer vision, edge deployment, or autonomous systems roles."
        if "erev" in lowered or "electric" in lowered or "vehicle" in lowered or "emissions" in lowered:
            return "Use for EV, energy, sustainability, transportation, analytics, or research roles."
        if "ictcs" in lowered:
            return "Use for healthcare AI, ML survey, AI governance, or research roles."
        if "resume" in lowered:
            return "Base resume source of truth for public profile facts."
        if "instruction" in lowered:
            return "Tailoring instructions and constraints."
        return "Use only when the JD clearly connects to this artifact."

    @staticmethod
    def _truncate_context(context: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
        text_len = len(str(context))
        if text_len <= max_chars:
            return context

        remaining = max_chars
        trimmed = dict(context)
        instructions = str(trimmed.get("instructions") or "")
        trimmed["instructions"] = instructions[: min(len(instructions), 5000)]
        remaining -= len(str(trimmed["instructions"]))

        summaries = []
        for item in context.get("evidence_summaries", []):
            source = str(item.get("source") or "")
            text = str(item.get("text") or "")
            per_summary = max(1200, remaining // max(1, len(context.get("evidence_summaries", []))))
            summaries.append({"source": source, "text": text[:per_summary]})
        trimmed["evidence_summaries"] = summaries
        return trimmed
