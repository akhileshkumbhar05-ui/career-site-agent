from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

SEEN_JOBS_PATH = Path("data/seen_jobs.json")
EVICT_AFTER_DAYS = 30


class SeenJobsStore:
    """Persist job IDs that have already been sent to n8n."""

    def __init__(self, path: Path = SEEN_JOBS_PATH) -> None:
        self.path = path
        self._store: dict[str, str] = {}
        self._load()

    def is_seen(self, job_id: str) -> bool:
        return job_id in self._store

    def mark_seen(self, job_id: str) -> None:
        self._store[job_id] = datetime.now(UTC).isoformat()
        self._save()

    def mark_seen_batch(self, job_ids: list[str]) -> None:
        now = datetime.now(UTC).isoformat()
        for job_id in job_ids:
            self._store[job_id] = now
        self._save()

    def evict_old(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=EVICT_AFTER_DAYS)
        to_remove: list[str] = []

        for job_id, timestamp in self._store.items():
            try:
                if datetime.fromisoformat(timestamp) < cutoff:
                    to_remove.append(job_id)
            except ValueError:
                to_remove.append(job_id)

        for job_id in to_remove:
            self._store.pop(job_id, None)

        if to_remove:
            self._save()
            logger.info("Evicted %d old seen-job entries", len(to_remove))

        return len(to_remove)

    def __len__(self) -> int:
        return len(self._store)

    def _load(self) -> None:
        if not self.path.exists():
            self._store = {}
            return

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not load seen-job store %s: %s", self.path, exc)
            self._store = {}
            return

        self._store = data if isinstance(data, dict) else {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._store, indent=2), encoding="utf-8")
