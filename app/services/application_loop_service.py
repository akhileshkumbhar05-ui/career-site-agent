from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import json
import re
import sqlite3
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from app.db import get_db_connection, init_db
from app.schemas.application_loop import (
    ApplicationLoopBatchImportRequest,
    ApplicationLoopBatchItemRequest,
    ApplicationLoopBatchOutcome,
    ApplicationLoopBatchResponse,
    ApplicationLoopBatchSummary,
    ApplicationLoopCreateRequest,
    ApplicationLoopEvent,
    ApplicationLoopItem,
    ApplicationLoopState,
    ApplicationLoopTransitionRequest,
)
from app.services.tracker_service import TrackerService


ALLOWED_TRANSITIONS: dict[ApplicationLoopState, tuple[ApplicationLoopState, ...]] = {
    "imported": ("fit_checked", "skipped"),
    "fit_checked": ("draft_ready", "skipped"),
    "skipped": (),
    "draft_ready": ("revision_requested", "approved_for_apply", "skipped"),
    "revision_requested": ("draft_ready", "skipped"),
    "approved_for_apply": ("revision_requested", "ats_opened", "submitted_confirmed", "skipped"),
    "ats_opened": ("revision_requested", "submitted_confirmed", "skipped"),
    "submitted_confirmed": ("sheet_logged", "recruiter_note_ready"),
    "sheet_logged": ("recruiter_note_ready",),
    "recruiter_note_ready": ("outreach_done",),
    "outreach_done": (),
}


class InvalidApplicationLoopTransition(ValueError):
    pass


class ApplicationLoopService:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        init_db()

    def create(self, payload: ApplicationLoopCreateRequest) -> ApplicationLoopItem:
        now = self._now()
        loop_id = payload.lead_id.strip() or f"loop_{uuid4().hex}"
        initial_event = ApplicationLoopEvent(
            to_state="imported",
            actor=payload.actor,
            note="Job added to the application loop.",
            occurred_at=now,
        )
        return ApplicationLoopItem(
            loop_id=loop_id,
            company=payload.company.strip(),
            role=payload.role.strip(),
            job_url=payload.job_url.strip(),
            source=payload.source.strip() or "Unknown",
            created_at=now,
            updated_at=now,
            history=[initial_event],
        )

    def transition(
        self,
        item: ApplicationLoopItem,
        payload: ApplicationLoopTransitionRequest,
    ) -> ApplicationLoopItem:
        allowed = ALLOWED_TRANSITIONS[item.state]
        if payload.target_state not in allowed:
            choices = ", ".join(allowed) if allowed else "none"
            raise InvalidApplicationLoopTransition(
                f"Cannot move application loop from '{item.state}' to "
                f"'{payload.target_state}'. Allowed next states: {choices}."
            )

        if payload.target_state == "submitted_confirmed":
            if payload.actor != "human" or not payload.human_confirmed_submission:
                raise InvalidApplicationLoopTransition(
                    "submitted_confirmed requires an explicit human confirmation of manual submission."
                )

        now = self._now()
        updated = item.model_copy(deep=True)
        updated.state = payload.target_state
        updated.updated_at = now
        if payload.target_state == "revision_requested":
            updated.revision_count += 1
        updated.history.append(
            ApplicationLoopEvent(
                from_state=item.state,
                to_state=payload.target_state,
                actor=payload.actor,
                note=payload.note.strip(),
                occurred_at=now,
                human_confirmed_submission=payload.human_confirmed_submission,
            )
        )
        return updated

    @staticmethod
    def allowed_next_states(state: ApplicationLoopState) -> tuple[ApplicationLoopState, ...]:
        return ALLOWED_TRANSITIONS[state]

    def import_batch(self, payload: ApplicationLoopBatchImportRequest) -> ApplicationLoopBatchResponse:
        batch_id = f"batch_{uuid4().hex}"
        created_at = self._now()
        outcomes: list[ApplicationLoopBatchOutcome] = []

        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO application_loop_batches (
                    batch_id,
                    created_at,
                    requested_count,
                    imported_count,
                    duplicate_count,
                    invalid_count
                )
                VALUES (?, ?, ?, 0, 0, 0)
                """,
                (batch_id, created_at, len(payload.items)),
            )

            for input_index, raw_item in enumerate(payload.items):
                normalized, error = self._normalize_batch_item(raw_item)
                if error:
                    outcome = ApplicationLoopBatchOutcome(
                        input_index=input_index,
                        status="invalid",
                        reason=error,
                    )
                else:
                    company, role, job_url, canonical_url, jd_text, source = normalized
                    duplicate_row, duplicate_reason = self._find_duplicate(
                        conn,
                        canonical_url=canonical_url,
                        company=company,
                        role=role,
                    )
                    if duplicate_row is not None:
                        outcome = ApplicationLoopBatchOutcome(
                            input_index=input_index,
                            status="duplicate",
                            reason=duplicate_reason,
                            loop_item=self._row_to_item(duplicate_row),
                        )
                    else:
                        loop_item = self.create(
                            ApplicationLoopCreateRequest(
                                company=company,
                                role=role,
                                job_url=job_url,
                                source=source,
                                actor="system",
                            )
                        )
                        loop_item.batch_id = batch_id
                        loop_item.canonical_job_url = canonical_url
                        loop_item.jd_text = jd_text
                        conn.execute(
                            """
                            INSERT INTO application_loop_items (
                                loop_id,
                                batch_id,
                                canonical_job_url,
                                normalized_company,
                                normalized_role,
                                item_json,
                                created_at,
                                updated_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                loop_item.loop_id,
                                batch_id,
                                canonical_url or None,
                                self._normalize_match_text(company),
                                self._normalize_match_text(role),
                                loop_item.model_dump_json(),
                                loop_item.created_at,
                                loop_item.updated_at,
                            ),
                        )
                        outcome = ApplicationLoopBatchOutcome(
                            input_index=input_index,
                            status="imported",
                            reason="Added to the application loop.",
                            loop_item=loop_item,
                        )

                outcomes.append(outcome)
                conn.execute(
                    """
                    INSERT INTO application_loop_batch_outcomes (
                        batch_id,
                        input_index,
                        status,
                        reason,
                        loop_id,
                        input_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        batch_id,
                        input_index,
                        outcome.status,
                        outcome.reason,
                        outcome.loop_item.loop_id if outcome.loop_item else None,
                        raw_item.model_dump_json(),
                    ),
                )

            summary = self._summarize(outcomes)
            conn.execute(
                """
                UPDATE application_loop_batches
                SET imported_count = ?, duplicate_count = ?, invalid_count = ?
                WHERE batch_id = ?
                """,
                (summary.imported, summary.duplicate, summary.invalid, batch_id),
            )
            conn.commit()
        except (sqlite3.DatabaseError, ValueError):
            conn.rollback()
            raise
        finally:
            conn.close()

        return ApplicationLoopBatchResponse(
            batch_id=batch_id,
            created_at=created_at,
            summary=summary,
            outcomes=outcomes,
        )

    def list_items(self, *, limit: int = 100) -> list[ApplicationLoopItem]:
        conn = get_db_connection()
        try:
            rows = conn.execute(
                """
                SELECT item_json
                FROM application_loop_items
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_item(row) for row in rows]

    @classmethod
    def _normalize_batch_item(
        cls,
        item: ApplicationLoopBatchItemRequest,
    ) -> tuple[tuple[str, str, str, str, str, str] | None, str]:
        company = item.company.strip()
        role = item.role.strip()
        job_url = item.job_url.strip()
        jd_text = item.jd_text.strip()
        source = item.source.strip() or "Unknown"

        if not job_url and not jd_text:
            return None, "Add a job URL, a job description, or both."

        if job_url:
            parsed = urlsplit(job_url)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
                return None, "Job URL must be a complete http or https URL."
        else:
            parsed = None

        jd_company, jd_role = cls._extract_jd_identity(jd_text)
        company = company or jd_company
        role = role or jd_role

        if parsed is not None:
            company = company or cls._company_from_url(parsed)
            role = role or cls._role_from_url(parsed)

        if not company or not role:
            return None, "Company and role could not be inferred; add them to this entry."

        canonical_url = TrackerService.canonicalize_job_link(job_url)
        return (company, role, job_url, canonical_url, jd_text, source), ""

    @classmethod
    def _extract_jd_identity(cls, jd_text: str) -> tuple[str, str]:
        if not jd_text:
            return "", ""

        company = cls._match_labeled_line(jd_text, ("company", "organization", "employer"))
        role = cls._match_labeled_line(jd_text, ("job title", "title", "role", "position"))
        if company and role:
            return company, role

        lines = [re.sub(r"\s+", " ", line).strip() for line in jd_text.splitlines() if line.strip()]
        concise = [line for line in lines[:8] if len(line) <= 160 and not line.endswith(":")]
        if not role and concise:
            role = concise[0]
        if not company and len(concise) > 1 and len(concise[1]) <= 100:
            company = concise[1]
        return company, role

    @staticmethod
    def _match_labeled_line(text: str, labels: tuple[str, ...]) -> str:
        label_pattern = "|".join(re.escape(label) for label in labels)
        match = re.search(rf"^(?:{label_pattern})\s*[:\-]\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""

    @classmethod
    def _company_from_url(cls, parsed) -> str:
        host = parsed.netloc.lower().split(":", 1)[0]
        path_parts = [part for part in parsed.path.split("/") if part]
        ats_hosts = ("lever.co", "greenhouse.io", "ashbyhq.com", "smartrecruiters.com")
        if any(host.endswith(ats_host) for ats_host in ats_hosts) and path_parts:
            return cls._prettify_slug(path_parts[0])

        labels = [
            label
            for label in host.split(".")
            if label not in {"www", "jobs", "job", "careers", "career", "apply", "boards"}
        ]
        token = labels[-2] if len(labels) >= 2 else labels[0] if labels else ""
        return cls._prettify_slug(token)

    @classmethod
    def _role_from_url(cls, parsed) -> str:
        generic = {
            "apply",
            "career",
            "careers",
            "job",
            "jobs",
            "jobdetail",
            "openings",
            "opportunities",
            "position",
            "positions",
            "view",
        }
        numeric_id = ""
        for raw_part in reversed([part for part in parsed.path.split("/") if part]):
            part = unquote(raw_part).split(".", 1)[0]
            numbers = re.findall(r"\d{4,}", part)
            if numbers and not numeric_id:
                numeric_id = numbers[0]
            slug = re.sub(r"^\d+[\-_]*|[\-_]*\d+$", "", part).strip("-_")
            if slug.casefold() in generic or not re.search(r"[A-Za-z]", slug):
                continue
            if len(slug) >= 4:
                return cls._prettify_slug(slug)
        return f"Job {numeric_id}" if numeric_id else ""

    @staticmethod
    def _prettify_slug(value: str) -> str:
        words = re.sub(r"[-_]+", " ", value).strip()
        return re.sub(r"\s+", " ", words).title()

    @classmethod
    def _find_duplicate(
        cls,
        conn: sqlite3.Connection,
        *,
        canonical_url: str,
        company: str,
        role: str,
    ) -> tuple[sqlite3.Row | None, str]:
        if canonical_url:
            row = conn.execute(
                "SELECT item_json FROM application_loop_items WHERE canonical_job_url = ?",
                (canonical_url,),
            ).fetchone()
            if row is not None:
                return row, "Canonical job link already exists in the inbox."

        row = conn.execute(
            """
            SELECT item_json
            FROM application_loop_items
            WHERE normalized_company = ? AND normalized_role = ?
            """,
            (cls._normalize_match_text(company), cls._normalize_match_text(role)),
        ).fetchone()
        if row is not None:
            return row, "Company and role already exist in the inbox."
        return None, ""

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> ApplicationLoopItem:
        return ApplicationLoopItem.model_validate(json.loads(row["item_json"]))

    @staticmethod
    def _summarize(outcomes: list[ApplicationLoopBatchOutcome]) -> ApplicationLoopBatchSummary:
        return ApplicationLoopBatchSummary(
            requested=len(outcomes),
            imported=sum(outcome.status == "imported" for outcome in outcomes),
            duplicate=sum(outcome.status == "duplicate" for outcome in outcomes),
            invalid=sum(outcome.status == "invalid" for outcome in outcomes),
        )

    @staticmethod
    def _normalize_match_text(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip()).casefold()

    def _now(self) -> str:
        return self._clock().astimezone(UTC).isoformat()
