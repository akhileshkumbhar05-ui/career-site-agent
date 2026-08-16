from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import sqlite3
from uuid import uuid4

from app.db import get_db_connection, init_db
from app.schemas.application_loop import ApplicationLoopItem
from app.schemas.application_sprint import (
    ApplicationSprintAddItemsRequest,
    ApplicationSprintCreateRequest,
    ApplicationSprintItem,
    ApplicationSprintNextAction,
    ApplicationSprintResponse,
    ApplicationSprintStats,
)
from app.services.application_loop_service import ApplicationLoopService


SUBMITTED_STATES = {"submitted_confirmed", "sheet_logged", "recruiter_note_ready", "outreach_done"}
SHEETS_STATES = {"sheet_logged", "recruiter_note_ready", "outreach_done"}
FINISHED_APPLICATION_STATES = {"sheet_logged", "recruiter_note_ready", "outreach_done"}


class ApplicationSprintConflict(ValueError):
    pass


class ApplicationSprintService:
    def __init__(
        self,
        *,
        loop_service: ApplicationLoopService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.loop_service = loop_service
        self._clock = clock or (lambda: datetime.now(UTC))
        init_db()

    def create(self, payload: ApplicationSprintCreateRequest) -> ApplicationSprintResponse:
        current = self.current()
        if current and current.status in {"active", "paused"}:
            raise ApplicationSprintConflict("Pause, finish, or resume the current sprint before starting another.")
        if current and not current.ready_for_next_sprint:
            raise ApplicationSprintConflict(
                "Finish Sheets logging and recruiter outreach for the completed sprint before starting another."
            )
        now = self._now()
        loop_items = [self.loop_service.get_item(loop_id) for loop_id in payload.loop_ids]
        sprint_id = f"sprint_{uuid4().hex}"
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT sprint_id FROM application_sprints WHERE status IN ('active', 'paused') LIMIT 1"
            ).fetchone()
            if existing:
                raise ApplicationSprintConflict("Pause, finish, or resume the current sprint before starting another.")
            conn.execute(
                """
                INSERT INTO application_sprints (
                    sprint_id, name, status, target_count, started_at, paused_at,
                    completed_at, total_paused_seconds, created_at, updated_at
                ) VALUES (?, ?, 'active', ?, ?, NULL, NULL, 0, ?, ?)
                """,
                (sprint_id, payload.name.strip(), payload.target_count, now, now, now),
            )
            for position, item in enumerate(loop_items, start=1):
                conn.execute(
                    """
                    INSERT INTO application_sprint_items (sprint_id, loop_id, position, added_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (sprint_id, item.loop_id, position, now),
                )
            conn.commit()
        except (sqlite3.DatabaseError, ValueError):
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.get(sprint_id)

    def current(self) -> ApplicationSprintResponse | None:
        conn = get_db_connection()
        try:
            row = conn.execute(
                """
                SELECT sprint_id
                FROM application_sprints
                ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,
                         updated_at DESC
                LIMIT 1
                """
            ).fetchone()
        finally:
            conn.close()
        return self.get(row["sprint_id"]) if row else None

    def get(self, sprint_id: str) -> ApplicationSprintResponse:
        row, item_rows = self._load(sprint_id)
        loop_items = [self.loop_service.get_item(item_row["loop_id"]) for item_row in item_rows]
        submitted_count = sum(item.state in SUBMITTED_STATES for item in loop_items)
        if row["status"] != "completed" and submitted_count >= row["target_count"]:
            self._complete(sprint_id)
            row, item_rows = self._load(sprint_id)

        active_items = [item for item in loop_items if item.state != "skipped"]
        current_loop_id = next(
            (
                item.loop_id
                for item in loop_items
                if item.state != "skipped" and item.state not in FINISHED_APPLICATION_STATES
            ),
            "",
        )
        outreach_unlocked = submitted_count >= row["target_count"]
        outreach_loop_ids = [item.loop_id for item in loop_items if item.state in SUBMITTED_STATES]
        ready_for_next_sprint = (
            row["status"] == "completed"
            and len(active_items) >= row["target_count"]
            and all(item.state == "outreach_done" for item in active_items)
        )
        stats = ApplicationSprintStats(
            target_count=row["target_count"],
            active_job_count=len(active_items),
            history_count=len(loop_items),
            submitted_count=submitted_count,
            sheet_logged_count=sum(item.state in SHEETS_STATES for item in loop_items),
            skipped_count=sum(item.state == "skipped" for item in loop_items),
            open_slots=max(0, row["target_count"] - len(active_items)),
            revision_count=sum(item.revision_count for item in loop_items),
            claude_calls=self._claude_calls(loop_items),
            elapsed_seconds=self._elapsed_seconds(row),
        )
        return ApplicationSprintResponse(
            sprint_id=row["sprint_id"],
            name=row["name"],
            status=row["status"],
            started_at=row["started_at"],
            paused_at=row["paused_at"] or "",
            completed_at=row["completed_at"] or "",
            updated_at=row["updated_at"],
            current_loop_id=current_loop_id,
            outreach_unlocked=outreach_unlocked,
            ready_for_next_sprint=ready_for_next_sprint,
            outreach_loop_ids=outreach_loop_ids,
            stats=stats,
            items=[
                ApplicationSprintItem(
                    position=item_row["position"],
                    added_at=item_row["added_at"],
                    counted_toward_target=item.state != "skipped",
                    is_current=item.loop_id == current_loop_id,
                    next_action=self._next_action(item, outreach_unlocked),
                    loop_item=item,
                )
                for item_row, item in zip(item_rows, loop_items, strict=True)
            ],
        )

    def add_items(
        self,
        sprint_id: str,
        payload: ApplicationSprintAddItemsRequest,
    ) -> ApplicationSprintResponse:
        sprint = self.get(sprint_id)
        if sprint.status == "completed":
            raise ApplicationSprintConflict("A completed sprint cannot accept replacement jobs.")
        if len(payload.loop_ids) > sprint.stats.open_slots:
            raise ApplicationSprintConflict(
                f"This sprint has {sprint.stats.open_slots} open slot(s), but {len(payload.loop_ids)} jobs were supplied."
            )
        for loop_id in payload.loop_ids:
            self.loop_service.get_item(loop_id)

        now = self._now()
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = {
                row["loop_id"]
                for row in conn.execute(
                    "SELECT loop_id FROM application_sprint_items WHERE sprint_id = ?",
                    (sprint_id,),
                ).fetchall()
            }
            duplicate = existing.intersection(payload.loop_ids)
            if duplicate:
                raise ApplicationSprintConflict("A selected replacement job is already in this sprint.")
            max_position = conn.execute(
                "SELECT COALESCE(MAX(position), 0) AS value FROM application_sprint_items WHERE sprint_id = ?",
                (sprint_id,),
            ).fetchone()["value"]
            for offset, loop_id in enumerate(payload.loop_ids, start=1):
                conn.execute(
                    """
                    INSERT INTO application_sprint_items (sprint_id, loop_id, position, added_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (sprint_id, loop_id, max_position + offset, now),
                )
            conn.execute(
                "UPDATE application_sprints SET updated_at = ? WHERE sprint_id = ?",
                (now, sprint_id),
            )
            conn.commit()
        except (sqlite3.DatabaseError, ValueError):
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.get(sprint_id)

    def pause(self, sprint_id: str) -> ApplicationSprintResponse:
        row, _ = self._load(sprint_id)
        if row["status"] != "active":
            raise ApplicationSprintConflict("Only an active sprint can be paused.")
        now = self._now()
        self._update_status(sprint_id, status="paused", paused_at=now, updated_at=now)
        return self.get(sprint_id)

    def resume(self, sprint_id: str) -> ApplicationSprintResponse:
        row, _ = self._load(sprint_id)
        if row["status"] != "paused":
            raise ApplicationSprintConflict("Only a paused sprint can be resumed.")
        now_dt = self._clock()
        paused_at = self._parse(row["paused_at"])
        added_pause = max(0, int((now_dt - paused_at).total_seconds())) if paused_at else 0
        now = now_dt.isoformat()
        conn = get_db_connection()
        try:
            conn.execute(
                """
                UPDATE application_sprints
                SET status = 'active', paused_at = NULL,
                    total_paused_seconds = total_paused_seconds + ?, updated_at = ?
                WHERE sprint_id = ?
                """,
                (added_pause, now, sprint_id),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get(sprint_id)

    def _load(self, sprint_id: str):
        conn = get_db_connection()
        try:
            row = conn.execute(
                "SELECT * FROM application_sprints WHERE sprint_id = ?",
                (sprint_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Application sprint not found: {sprint_id}")
            item_rows = conn.execute(
                """
                SELECT loop_id, position, added_at
                FROM application_sprint_items
                WHERE sprint_id = ?
                ORDER BY position ASC
                """,
                (sprint_id,),
            ).fetchall()
            return row, item_rows
        finally:
            conn.close()

    def _complete(self, sprint_id: str) -> None:
        now = self._now()
        conn = get_db_connection()
        try:
            row = conn.execute(
                "SELECT status, paused_at, total_paused_seconds FROM application_sprints WHERE sprint_id = ?",
                (sprint_id,),
            ).fetchone()
            if row is None or row["status"] == "completed":
                return
            paused_seconds = row["total_paused_seconds"]
            if row["paused_at"]:
                paused_seconds += max(0, int((self._clock() - self._parse(row["paused_at"])).total_seconds()))
            conn.execute(
                """
                UPDATE application_sprints
                SET status = 'completed', completed_at = ?, paused_at = NULL,
                    total_paused_seconds = ?, updated_at = ?
                WHERE sprint_id = ?
                """,
                (now, paused_seconds, now, sprint_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _update_status(self, sprint_id: str, **values: str) -> None:
        assignments = ", ".join(f"{key} = ?" for key in values)
        conn = get_db_connection()
        try:
            conn.execute(
                f"UPDATE application_sprints SET {assignments} WHERE sprint_id = ?",
                (*values.values(), sprint_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _elapsed_seconds(self, row) -> int:
        started_at = self._parse(row["started_at"])
        end = self._parse(row["completed_at"]) if row["completed_at"] else self._clock()
        paused = int(row["total_paused_seconds"])
        if row["status"] == "paused" and row["paused_at"]:
            paused += max(0, int((self._clock() - self._parse(row["paused_at"])).total_seconds()))
        return max(0, int((end - started_at).total_seconds()) - paused)

    @staticmethod
    def _next_action(item: ApplicationLoopItem, outreach_unlocked: bool) -> ApplicationSprintNextAction:
        if item.state == "skipped":
            return ApplicationSprintNextAction(
                key="replace_job", label="Replace job", detail="This job no longer occupies a sprint slot.", manual_gate=True
            )
        if item.state == "imported":
            if len(item.jd_text.strip()) < 20:
                return ApplicationSprintNextAction(
                    key="add_jd", label="Add job description", detail="Paste the JD before Fit Gate can run.", manual_gate=True
                )
            return ApplicationSprintNextAction(
                key="run_fit_gate", label="Run Fit Gate", detail="Check whether this role deserves tailoring."
            )
        if item.state == "fit_checked":
            if item.fit_gate and item.fit_gate.decision == "maybe":
                return ApplicationSprintNextAction(
                    key="review_fit", label="Review fit", detail="Resolve the maybe decision before tailoring.", manual_gate=True
                )
            return ApplicationSprintNextAction(
                key="tailor_resume", label="Tailor resume", detail="Choose tailoring controls and create the first draft."
            )
        if item.state == "revision_requested":
            return ApplicationSprintNextAction(
                key="wait_for_draft", label="Finish revision", detail="Complete the requested Claude revision."
            )
        if item.state == "draft_ready":
            return ApplicationSprintNextAction(
                key="review_resume", label="Review resume", detail="Approve it or request another grounded revision.", manual_gate=True
            )
        if item.state == "approved_for_apply":
            if not item.export_handoff:
                return ApplicationSprintNextAction(
                    key="export_resume", label="Export resume", detail="Generate the approved DOCX and PDF.", manual_gate=True
                )
            return ApplicationSprintNextAction(
                key="open_ats", label="Open ATS", detail="Open the application with the approved resume ready.", manual_gate=True
            )
        if item.state == "ats_opened":
            if item.ats_assist and item.ats_assist.status == "technical_issue":
                return ApplicationSprintNextAction(
                    key="resolve_portal_issue", label="Resolve portal issue", detail="Reopen the ATS after reviewing the recorded issue.", manual_gate=True
                )
            return ApplicationSprintNextAction(
                key="confirm_submission", label="Confirm submission", detail="Only confirm after the ATS shows success.", manual_gate=True
            )
        if item.state == "submitted_confirmed":
            return ApplicationSprintNextAction(
                key="log_sheets", label="Log to Sheets", detail="Append the confirmed application using the canonical columns.", manual_gate=True
            )
        if item.state == "sheet_logged":
            if outreach_unlocked:
                return ApplicationSprintNextAction(
                    key="ready_for_outreach", label="Prepare outreach", detail="The sprint target is confirmed; recruiter notes are unlocked."
                )
            return ApplicationSprintNextAction(
                key="done", label="Application complete", detail="Move to the next sprint job."
            )
        if item.state == "recruiter_note_ready":
            return ApplicationSprintNextAction(
                key="review_outreach", label="Review outreach", detail="Review and manually send the LinkedIn connection request.", manual_gate=True
            )
        return ApplicationSprintNextAction(
            key="done", label="Done", detail="Application and recruiter outreach are complete."
        )

    @staticmethod
    def _claude_calls(items: list[ApplicationLoopItem]) -> int:
        fit_calls = sum(
            bool(result.used_llm and not result.cache_hit and not result.overridden)
            for item in items
            for result in item.fit_gate_history
        )
        tailoring_calls = sum(
            bool(draft.claude_call_consumed)
            for item in items
            for draft in item.tailoring_history
        )
        outreach_calls = {
            (item.recruiter_outreach.generated_at, item.recruiter_outreach.model)
            for item in items
            if item.recruiter_outreach and item.recruiter_outreach.claude_call_consumed
        }
        return fit_calls + tailoring_calls + len(outreach_calls)

    def _now(self) -> str:
        return self._clock().isoformat()

    @staticmethod
    def _parse(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None
