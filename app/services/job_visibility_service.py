from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


class JobVisibilityService:
    """Tracks jobs the user wants hidden from the recommendation UI."""

    def __init__(self, state_path: str = "data/runtime/job_visibility.json") -> None:
        self.state_path = Path(state_path)

    def job_key(self, job: dict[str, Any]) -> str:
        url = self.resolve_url(job)
        if url:
            return f"url:{self._normalize_url(url)}"

        return "job:" + "|".join(
            [
                self._normalize_text(str(job.get("company") or "")),
                self._normalize_text(str(job.get("title") or job.get("role") or "")),
                self._normalize_text(str(job.get("location") or "")),
            ]
        )

    def resolve_url(self, job: dict[str, Any]) -> str:
        return str(
            job.get("discovered_url")
            or job.get("official_url")
            or job.get("url")
            or job.get("link")
            or ""
        ).strip()

    def mark_hidden(self, job: dict[str, Any], *, reason: str = "already_applied") -> dict[str, Any]:
        state = self._load_state()
        key = self.job_key(job)
        record = {
            "key": key,
            "reason": reason,
            "company": str(job.get("company") or ""),
            "title": str(job.get("title") or job.get("role") or ""),
            "url": self.resolve_url(job),
            "hidden_at": datetime.now(UTC).isoformat(),
            "job": self._job_snapshot(job),
        }
        state.setdefault("hidden_jobs", {})[key] = record
        self._save_state(state)
        return record

    def mark_applied(self, job: dict[str, Any]) -> dict[str, Any]:
        return self.mark_hidden(job, reason="already_applied")

    def list_hidden(self, *, reason: str | None = None) -> list[dict[str, Any]]:
        records = list(self._load_state().get("hidden_jobs", {}).values())
        if reason:
            records = [record for record in records if record.get("reason") == reason]
        return sorted(records, key=lambda record: str(record.get("hidden_at") or ""), reverse=True)

    def applied_jobs(self) -> list[dict[str, Any]]:
        return self.list_hidden(reason="already_applied")

    def is_hidden(self, job: dict[str, Any]) -> bool:
        return self.job_key(job) in self._load_state().get("hidden_jobs", {})

    def hidden_reason(self, job: dict[str, Any]) -> str:
        record = self._load_state().get("hidden_jobs", {}).get(self.job_key(job), {})
        return str(record.get("reason") or "")

    def matches_applied_tracker_row(self, job: dict[str, Any], tracker_row: Any) -> bool:
        row_link = str(getattr(tracker_row, "link", "") or "")
        job_url = self.resolve_url(job)
        if row_link and job_url and self._normalize_url(row_link) == self._normalize_url(job_url):
            return True

        job_company = self._normalize_text(str(job.get("company") or ""))
        job_title = self._normalize_text(str(job.get("title") or job.get("role") or ""))
        row_company = self._normalize_text(str(getattr(tracker_row, "company_applied", "") or ""))
        row_role = self._normalize_text(str(getattr(tracker_row, "role", "") or ""))

        if not job_company or not job_title or not row_company or not row_role:
            return False

        company_matches = job_company == row_company or job_company in row_company or row_company in job_company
        title_matches = job_title == row_role or job_title in row_role or row_role in job_title
        return company_matches and title_matches

    def is_applied_in_tracker(self, job: dict[str, Any], tracker_rows: list[Any]) -> bool:
        return any(self.matches_applied_tracker_row(job, row) for row in tracker_rows)

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"hidden_jobs": {}}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"hidden_jobs": {}}
        if not isinstance(data, dict):
            return {"hidden_jobs": {}}
        data.setdefault("hidden_jobs", {})
        return data

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_url(value: str) -> str:
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

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    def _job_snapshot(self, job: dict[str, Any]) -> dict[str, Any]:
        snapshot = self._json_safe(job)
        if not isinstance(snapshot, dict):
            snapshot = {}
        snapshot.setdefault("discovered_url", self.resolve_url(job))
        return snapshot

    def _json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(item) for item in value]
        return str(value)
