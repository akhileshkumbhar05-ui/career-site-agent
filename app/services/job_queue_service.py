from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.db import get_db_connection, init_db
from app.schemas.pipeline import JobProcessRequest
from app.schemas.queue import (
    QueueClaimRequest,
    QueueCompleteRequest,
    QueueEnqueueRequest,
    QueueEnqueueResponse,
    JobQueueItem,
    QueueStatus,
    TERMINAL_QUEUE_STATUSES,
)


class JobQueueService:
    def __init__(self) -> None:
        init_db()

    def enqueue(self, payload: QueueEnqueueRequest) -> QueueEnqueueResponse:
        now = self._now()
        fingerprint = self._fingerprint(payload.job)
        queue_id = f"job_{fingerprint[:20]}"

        conn = get_db_connection()
        try:
            try:
                conn.execute(
                    """
                    INSERT INTO job_queue (
                        queue_id,
                        fingerprint,
                        source_job_id,
                        company,
                        title,
                        jd_text,
                        discovered_url,
                        source,
                        posted_at,
                        location,
                        status,
                        priority,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        queue_id,
                        fingerprint,
                        payload.job.job_id,
                        payload.job.company,
                        payload.job.title,
                        payload.job.jd_text,
                        payload.job.discovered_url,
                        payload.job.source,
                        payload.job.posted_at,
                        payload.job.location,
                        "discovered",
                        payload.priority,
                        now,
                        now,
                    ),
                )
                conn.commit()
                return QueueEnqueueResponse(
                    queue_id=queue_id,
                    status="discovered",
                    duplicate=False,
                    message="Job lead queued.",
                )
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT queue_id, status FROM job_queue WHERE fingerprint = ?",
                    (fingerprint,),
                ).fetchone()
        finally:
            conn.close()

        if row is None:
            raise RuntimeError("Duplicate queue item was detected but could not be loaded.")

        return QueueEnqueueResponse(
            queue_id=row["queue_id"],
            status=row["status"],
            duplicate=True,
            message="Job lead already exists in the queue.",
        )

    def claim(self, payload: QueueClaimRequest) -> list[JobQueueItem]:
        now = self._now()
        locked_until = (datetime.now(UTC) + timedelta(seconds=payload.lease_seconds)).isoformat()
        statuses = payload.statuses or ["discovered"]
        placeholders = ",".join("?" for _ in statuses)

        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                f"""
                SELECT *
                FROM job_queue
                WHERE status IN ({placeholders})
                  AND (locked_until IS NULL OR locked_until <= ?)
                ORDER BY priority ASC, created_at ASC
                LIMIT ?
                """,
                (*statuses, now, payload.limit),
            ).fetchall()

            queue_ids = [row["queue_id"] for row in rows]
            if queue_ids:
                id_placeholders = ",".join("?" for _ in queue_ids)
                conn.execute(
                    f"""
                    UPDATE job_queue
                    SET
                        status = 'processing',
                        attempts = attempts + 1,
                        locked_by = ?,
                        locked_until = ?,
                        updated_at = ?
                    WHERE queue_id IN ({id_placeholders})
                    """,
                    (payload.worker_id, locked_until, now, *queue_ids),
                )
            conn.commit()
        finally:
            conn.close()

        return [self.get_item(queue_id) for queue_id in queue_ids]

    def complete(self, queue_id: str, payload: QueueCompleteRequest) -> JobQueueItem:
        now = self._now()
        completed_at = now if payload.status in TERMINAL_QUEUE_STATUSES else None
        result_json = json.dumps(payload.result, indent=2) if payload.result else None

        conn = get_db_connection()
        try:
            cursor = conn.execute(
                """
                UPDATE job_queue
                SET
                    status = ?,
                    locked_by = NULL,
                    locked_until = NULL,
                    result_json = ?,
                    error = ?,
                    updated_at = ?,
                    completed_at = COALESCE(?, completed_at)
                WHERE queue_id = ?
                """,
                (
                    payload.status,
                    result_json,
                    payload.error,
                    now,
                    completed_at,
                    queue_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        if cursor.rowcount == 0:
            raise KeyError(f"Queue item not found: {queue_id}")

        return self.get_item(queue_id)

    def release(self, queue_id: str, next_status: QueueStatus = "discovered", error: str = "") -> JobQueueItem:
        return self.complete(
            queue_id,
            QueueCompleteRequest(status=next_status, result={}, error=error),
        )

    def get_item(self, queue_id: str) -> JobQueueItem:
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT * FROM job_queue WHERE queue_id = ?", (queue_id,)).fetchone()
        finally:
            conn.close()

        if row is None:
            raise KeyError(f"Queue item not found: {queue_id}")

        return self._row_to_item(row)

    def list_items(self, status: QueueStatus | None = None, limit: int = 100) -> list[JobQueueItem]:
        conn = get_db_connection()
        try:
            if status:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM job_queue
                    WHERE status = ?
                    ORDER BY priority ASC, created_at ASC
                    LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM job_queue
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        finally:
            conn.close()

        return [self._row_to_item(row) for row in rows]

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> JobQueueItem:
        result = None
        if row["result_json"]:
            try:
                result = json.loads(row["result_json"])
            except json.JSONDecodeError:
                result = {"raw": row["result_json"]}

        return JobQueueItem(
            queue_id=row["queue_id"],
            fingerprint=row["fingerprint"],
            job=JobProcessRequest(
                job_id=row["source_job_id"],
                company=row["company"],
                title=row["title"],
                jd_text=row["jd_text"],
                discovered_url=row["discovered_url"],
                source=row["source"],
                posted_at=row["posted_at"],
                location=row["location"],
            ),
            status=row["status"],
            priority=row["priority"],
            attempts=row["attempts"],
            locked_by=row["locked_by"],
            locked_until=row["locked_until"],
            result=result,
            error=row["error"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )

    @classmethod
    def _fingerprint(cls, job: JobProcessRequest) -> str:
        key = "|".join(
            [
                cls._normalize_text(job.company),
                cls._normalize_text(job.title),
                cls._normalize_url(job.discovered_url) or cls._normalize_text(job.job_id),
                cls._normalize_text(job.location or ""),
            ]
        )
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

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

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
