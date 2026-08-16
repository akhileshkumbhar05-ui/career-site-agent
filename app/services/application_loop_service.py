from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from statistics import median
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from fastapi import HTTPException

from app.db import get_db_connection, init_db
from app.schemas.application_loop import (
    ApplicationLoopATSArmRequest,
    ApplicationLoopATSAssist,
    ApplicationLoopATSAssistResponse,
    ApplicationLoopATSOutcomeRequest,
    ApplicationLoopATSOutcomeResponse,
    ApplicationLoopATSReviewItem,
    ApplicationLoopBatchImportRequest,
    ApplicationLoopBatchItemReview,
    ApplicationLoopBatchItemRequest,
    ApplicationLoopBatchOutcome,
    ApplicationLoopBatchResponse,
    ApplicationLoopBatchSummary,
    ApplicationLoopCreateRequest,
    ApplicationLoopEvent,
    ApplicationLoopExportHandoff,
    ApplicationLoopFitGateOutcome,
    ApplicationLoopFitGateResponse,
    ApplicationLoopFitGateResult,
    ApplicationLoopFitGateRunRequest,
    ApplicationLoopFitGateSummary,
    ApplicationLoopFitOverrideRequest,
    ApplicationLoopItem,
    ApplicationLoopJDUpdateRequest,
    ApplicationLoopMetricBottleneck,
    ApplicationLoopMetricFunnelStage,
    ApplicationLoopMetricReason,
    ApplicationLoopMetricsResponse,
    ApplicationLoopMetricsSummary,
    ApplicationLoopMetricsWindow,
    ApplicationLoopMetricTiming,
    ApplicationLoopOutreachBatchOutcome,
    ApplicationLoopOutreachBatchRequest,
    ApplicationLoopOutreachBatchResponse,
    ApplicationLoopOutreachBatchSummary,
    ApplicationLoopOutreachCompanyGroup,
    ApplicationLoopOutreachResponse,
    ApplicationLoopOutreachSentRequest,
    ApplicationLoopOutreachUpdateRequest,
    ApplicationLoopRecruiterOutreach,
    ApplicationLoopSheetLoggedRequest,
    ApplicationLoopState,
    ApplicationLoopTailoringApproval,
    ApplicationLoopTailoringApproveRequest,
    ApplicationLoopTailoringApproveResponse,
    ApplicationLoopTailoringDraftRef,
    ApplicationLoopTailoringDraftRequest,
    ApplicationLoopTailoringDraftResponse,
    ApplicationLoopTailoringExportRequest,
    ApplicationLoopTailoringExportResponse,
    ApplicationLoopTailoringMemoryResponse,
    ApplicationLoopTailoringMemorySample,
    ApplicationLoopTransitionRequest,
)
from app.schemas.ats_autofill import AutofillAutopilotArmRequest
from app.schemas.resume import TailoringPreferences
from app.schemas.tailoring_review import (
    TailoringDraftRequest,
    TailoringFinalizeRequest,
    TailoringPreviewRenderResponse,
    TailoringReviewSelection,
)
from app.services.tracker_service import TrackerService
from app.services.recruiter_service import RecruiterService

if TYPE_CHECKING:
    from app.services.autofill_autopilot_service import AutofillAutopilotService
    from app.services.llm_match_service import LLMMatchService
    from app.services.recruiter_outreach_batch_service import RecruiterOutreachBatchService
    from app.services.tailoring_review_service import TailoringReviewService


ALLOWED_TRANSITIONS: dict[ApplicationLoopState, tuple[ApplicationLoopState, ...]] = {
    "imported": ("fit_checked", "skipped"),
    "fit_checked": ("draft_ready", "skipped"),
    "skipped": ("fit_checked",),
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
    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        matcher: LLMMatchService | None = None,
        tailoring_review: TailoringReviewService | None = None,
        autofill_autopilot: AutofillAutopilotService | None = None,
        recruiter_outreach: RecruiterOutreachBatchService | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self.matcher = matcher
        self.tailoring_review = tailoring_review
        self.autofill_autopilot = autofill_autopilot
        self.recruiter_outreach = recruiter_outreach
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

        if item.state == "skipped" and payload.target_state == "fit_checked":
            if payload.actor != "human" or not payload.note.strip():
                raise InvalidApplicationLoopTransition(
                    "Only a human can restore a skipped application after recording an override reason."
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

    def review_batch_item(self, raw_item: ApplicationLoopBatchItemRequest) -> ApplicationLoopBatchItemReview:
        normalized, error = self._normalize_batch_item(raw_item)
        if error:
            return ApplicationLoopBatchItemReview(valid=False, reason=error)

        company, role, job_url, canonical_url, jd_text, source = normalized
        conn = get_db_connection()
        try:
            duplicate_row, duplicate_reason = self._find_duplicate(
                conn,
                canonical_url=canonical_url,
                company=company,
                role=role,
            )
        finally:
            conn.close()

        return ApplicationLoopBatchItemReview(
            valid=True,
            normalized_item=ApplicationLoopBatchItemRequest(
                company=company,
                role=role,
                job_url=job_url,
                jd_text=jd_text,
                source=source,
            ),
            canonical_job_url=canonical_url,
            duplicate_reason=duplicate_reason,
            existing_loop_item=self._row_to_item(duplicate_row) if duplicate_row is not None else None,
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

    def get_item(self, loop_id: str) -> ApplicationLoopItem:
        conn = get_db_connection()
        try:
            row = conn.execute(
                "SELECT item_json FROM application_loop_items WHERE loop_id = ?",
                (loop_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise KeyError(f"Application loop item not found: {loop_id}")
        return self._row_to_item(row)

    def mark_sheet_logged(
        self,
        loop_id: str,
        payload: ApplicationLoopSheetLoggedRequest,
    ) -> ApplicationLoopItem:
        if not payload.sheet_write_succeeded:
            raise InvalidApplicationLoopTransition(
                "sheet_logged requires confirmation that the Sheets write succeeded or was a confirmed duplicate."
            )
        item = self.get_item(loop_id)
        updated = self.transition(
            item,
            ApplicationLoopTransitionRequest(
                target_state="sheet_logged",
                actor="human",
                note=payload.note,
            ),
        )
        self._save_item(updated)
        return updated

    def metrics(self, window: ApplicationLoopMetricsWindow = "7d") -> ApplicationLoopMetricsResponse:
        generated_at = self._now()
        now = self._parse_metric_timestamp(generated_at) or datetime.now(UTC)
        since = self._metrics_since(window, now)
        items = [
            item
            for item in self.list_items(limit=100_000)
            if since is None or (self._parse_metric_timestamp(item.created_at) or datetime.min.replace(tzinfo=UTC)) >= since
        ]

        reached = {
            state: sum(self._reached_state(item, state) for item in items)
            for state in ALLOWED_TRANSITIONS
        }
        total = len(items)
        funnel_states = (
            ("imported", "Imported", "milestone"),
            ("fit_checked", "Fit checked", "milestone"),
            ("skipped", "Skipped", "exit"),
            ("draft_ready", "Draft ready", "milestone"),
            ("approved_for_apply", "Approved", "milestone"),
            ("submitted_confirmed", "Submitted", "milestone"),
            ("sheet_logged", "Sheets logged", "milestone"),
            ("recruiter_note_ready", "Outreach ready", "milestone"),
            ("outreach_done", "Outreach sent", "milestone"),
        )
        funnel = [
            ApplicationLoopMetricFunnelStage(
                state=state,
                label=label,
                count=reached[state],
                percent_of_imported=self._percentage(reached[state], total),
                kind=kind,
            )
            for state, label, kind in funnel_states
        ]

        timing_specs = (
            ("intake_to_fit", "Intake to fit decision", "imported", ("fit_checked", "skipped"), "fit_checked"),
            ("fit_to_draft", "Fit decision to first draft", "fit_checked", ("draft_ready",), "draft_ready"),
            ("draft_to_approval", "First draft to approval", "draft_ready", ("approved_for_apply",), "approved_for_apply"),
            ("approval_to_submission", "Approval to submission", "approved_for_apply", ("submitted_confirmed",), "submitted_confirmed"),
            ("submission_to_sheets", "Submission to Sheets", "submitted_confirmed", ("sheet_logged",), "sheet_logged"),
            ("submission_to_outreach", "Submission to outreach note", "submitted_confirmed", ("recruiter_note_ready",), "recruiter_note_ready"),
            ("outreach_to_sent", "Outreach note to sent", "recruiter_note_ready", ("outreach_done",), "outreach_done"),
        )
        stage_timings: list[ApplicationLoopMetricTiming] = []
        for key, label, from_state, end_states, display_end_state in timing_specs:
            samples = self._transition_duration_samples(items, from_state, end_states)
            stage_timings.append(
                ApplicationLoopMetricTiming(
                    key=key,
                    label=label,
                    from_state=from_state,
                    to_state=display_end_state,
                    sample_count=len(samples),
                    average_minutes=self._average(samples),
                    median_minutes=round(float(median(samples)), 1) if samples else 0.0,
                )
            )

        completed_timings = [timing for timing in stage_timings if timing.sample_count]
        if completed_timings:
            slowest = max(completed_timings, key=lambda timing: timing.average_minutes)
            bottleneck = ApplicationLoopMetricBottleneck(
                key=slowest.key,
                label=slowest.label,
                average_minutes=slowest.average_minutes,
                sample_count=slowest.sample_count,
            )
        else:
            bottleneck = ApplicationLoopMetricBottleneck(
                label="Not enough completed transitions yet",
                average_minutes=0,
                sample_count=0,
            )

        tailored_items = [item for item in items if self._reached_state(item, "draft_ready")]
        score_lifts = [
            max(0, item.tailoring_draft.tailored_score - item.tailoring_draft.base_score)
            for item in tailored_items
            if item.tailoring_draft is not None
        ]
        submission_times = self._transition_duration_samples(
            items,
            "imported",
            ("submitted_confirmed",),
        )
        portal_issue_items = [
            item
            for item in items
            if item.ats_assist is not None
            and (
                item.ats_assist.status == "technical_issue"
                or bool(item.ats_assist.technical_issue_note.strip())
            )
        ]
        summary = ApplicationLoopMetricsSummary(
            total_applications=total,
            fit_checked=reached["fit_checked"],
            skipped=reached["skipped"],
            draft_ready=reached["draft_ready"],
            approved=reached["approved_for_apply"],
            submitted=reached["submitted_confirmed"],
            sheet_logged=reached["sheet_logged"],
            recruiter_note_ready=reached["recruiter_note_ready"],
            outreach_done=reached["outreach_done"],
            portal_issues=len(portal_issue_items),
            total_revisions=sum(item.revision_count for item in tailored_items),
            average_revisions_per_tailored=self._average(
                [float(item.revision_count) for item in tailored_items]
            ),
            average_tailoring_score_lift=self._average([float(value) for value in score_lifts]),
            average_minutes_to_submission=self._average(submission_times),
            submission_rate=self._percentage(reached["submitted_confirmed"], total),
            sheet_logging_rate=self._percentage(reached["sheet_logged"], reached["submitted_confirmed"]),
            outreach_completion_rate=self._percentage(reached["outreach_done"], reached["submitted_confirmed"]),
        )
        return ApplicationLoopMetricsResponse(
            window=window,
            window_label=self._metrics_window_label(window),
            since=since.isoformat() if since else "",
            generated_at=generated_at,
            summary=summary,
            funnel=funnel,
            stage_timings=stage_timings,
            bottleneck=bottleneck,
            skip_reasons=self._metric_reasons(
                event.note
                for item in items
                for event in item.history
                if event.to_state == "skipped" and event.note.strip()
            ),
            portal_failure_reasons=self._metric_reasons(
                item.ats_assist.technical_issue_note
                for item in portal_issue_items
                if item.ats_assist and item.ats_assist.technical_issue_note.strip()
            ),
            current_state_counts=dict(sorted(Counter(item.state for item in items).items())),
        )

    def tailoring_memory(
        self,
        role: str,
        *,
        exclude_loop_id: str = "",
    ) -> ApplicationLoopTailoringMemoryResponse:
        role_family = self._tailoring_role_family(role)
        role_family_label = self._tailoring_role_family_label(role_family, role)
        records: list[dict[str, Any]] = []

        for item in self.list_items(limit=100_000):
            approval = item.tailoring_approval
            if (
                item.loop_id == exclude_loop_id
                or approval is None
                or self._tailoring_role_family(item.role) != role_family
            ):
                continue
            reference = next(
                (
                    candidate
                    for candidate in reversed(item.tailoring_history)
                    if candidate.draft_id == approval.draft_id
                ),
                None,
            )
            if (
                reference is None
                and item.tailoring_draft is not None
                and item.tailoring_draft.draft_id == approval.draft_id
            ):
                reference = item.tailoring_draft
            if reference is None:
                continue
            preferences = self._tailoring_reference_preferences(reference)
            if preferences is None:
                continue

            final_emphasis = list(preferences.emphasis)
            review = approval.review
            if not review.summary_accepted:
                final_emphasis = [value for value in final_emphasis if value != "summary"]
            if review.project_ids:
                if "projects" not in final_emphasis:
                    final_emphasis.append("projects")
            else:
                final_emphasis = [value for value in final_emphasis if value != "projects"]
            if review.publication_ids:
                if "research_papers" not in final_emphasis:
                    final_emphasis.append("research_papers")
            else:
                final_emphasis = [value for value in final_emphasis if value != "research_papers"]

            approved_preferences = preferences.model_copy(
                deep=True,
                update={
                    "emphasis": final_emphasis,
                    "bullet_counts": review.bullet_counts,
                    "include_connection_note": bool(review.connection_note.strip()),
                    "include_cover_letter": bool(
                        review.cover_letter_accepted and review.cover_letter_text.strip()
                    ),
                },
            )
            revision_reasons = [
                candidate.revision_reason.strip()
                for candidate in item.tailoring_history
                if candidate.version <= reference.version and candidate.revision_reason.strip()
            ]
            records.append(
                {
                    "item": item,
                    "approval": approval,
                    "reference": reference,
                    "preferences": approved_preferences,
                    "revision_reasons": revision_reasons,
                    "instructions": [
                        *revision_reasons,
                        *(
                            [preferences.custom_instructions.strip()]
                            if preferences.custom_instructions.strip()
                            else []
                        ),
                    ],
                }
            )

        records.sort(
            key=lambda record: self._parse_metric_timestamp(record["approval"].approved_at)
            or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        if not records:
            return ApplicationLoopTailoringMemoryResponse(
                role_family=role_family,
                role_family_label=role_family_label,
                approved_sample_count=0,
                correction_count=0,
            )

        preferences = [record["preferences"] for record in records]
        instructions = self._dedupe_text(
            instruction
            for record in records
            for instruction in record["instructions"]
        )
        custom_instructions = self._tailoring_memory_instruction_text(instructions)
        recommended = TailoringPreferences(
            preset=self._recent_mode([value.preset for value in preferences]),
            rewrite_intensity=self._recent_mode(
                [value.rewrite_intensity for value in preferences]
            ),
            emphasis=list(
                self._recent_mode([tuple(value.emphasis) for value in preferences])
            ),
            custom_instructions=custom_instructions,
            include_connection_note=self._recent_mode(
                [value.include_connection_note for value in preferences]
            ),
            include_cover_letter=self._recent_mode(
                [value.include_cover_letter for value in preferences]
            ),
            bullet_counts={
                "experience_per_role": self._rounded_median(
                    [value.bullet_counts.experience_per_role for value in preferences]
                ),
                "projects_per_project": self._rounded_median(
                    [value.bullet_counts.projects_per_project for value in preferences]
                ),
                "research_per_paper": self._rounded_median(
                    [value.bullet_counts.research_per_paper for value in preferences]
                ),
            },
        )
        fingerprint_payload = {
            "role_family": role_family,
            "approvals": [
                {
                    "draft_id": record["reference"].draft_id,
                    "approved_at": record["approval"].approved_at,
                    "preferences": record["preferences"].model_dump(mode="json"),
                    "instructions": record["instructions"],
                }
                for record in records
            ],
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        source_roles = self._dedupe_text(record["item"].role for record in records)[:5]
        samples = [
            ApplicationLoopTailoringMemorySample(
                company=record["item"].company,
                role=record["item"].role,
                approved_at=record["approval"].approved_at,
                revision_count=len(record["revision_reasons"]),
            )
            for record in records[:5]
        ]
        return ApplicationLoopTailoringMemoryResponse(
            role_family=role_family,
            role_family_label=role_family_label,
            available=True,
            approved_sample_count=len(records),
            correction_count=len(instructions),
            recommended_preferences=recommended,
            learned_instructions=instructions[:5],
            source_roles=source_roles,
            samples=samples,
            latest_approval_at=records[0]["approval"].approved_at,
            fingerprint=fingerprint,
        )

    def run_fit_gate(self, payload: ApplicationLoopFitGateRunRequest) -> ApplicationLoopFitGateResponse:
        outcomes: list[ApplicationLoopFitGateOutcome] = []
        loop_ids = list(dict.fromkeys(loop_id.strip() for loop_id in payload.loop_ids if loop_id.strip()))

        for loop_id in loop_ids:
            try:
                item = self.get_item(loop_id)
                if item.state not in {"imported", "fit_checked", "skipped"}:
                    raise InvalidApplicationLoopTransition(
                        f"Fit Gate cannot run after the application reached '{item.state}'."
                    )

                if item.fit_gate is not None and (not payload.force_refresh or item.state == "skipped"):
                    status = "needs_jd" if item.fit_gate.evaluation_status == "needs_jd" else "cached"
                    outcomes.append(
                        ApplicationLoopFitGateOutcome(
                            loop_id=loop_id,
                            status=status,
                            result=item.fit_gate,
                            loop_item=item,
                        )
                    )
                    continue

                result = self._evaluate_fit_gate(
                    item,
                    use_llm=payload.use_llm,
                    force_refresh=payload.force_refresh,
                )
                updated = item.model_copy(deep=True)

                if result.evaluation_status == "complete":
                    target_state: ApplicationLoopState = "skipped" if result.decision == "skip" else "fit_checked"
                    if item.state == "imported" or (item.state == "fit_checked" and target_state == "skipped"):
                        updated = self.transition(
                            item,
                            ApplicationLoopTransitionRequest(
                                target_state=target_state,
                                actor="agent",
                                note=f"Fit Gate decision: {result.decision}. {result.one_line_reason}",
                            ),
                        )
                    else:
                        updated.updated_at = self._now()
                else:
                    updated.updated_at = self._now()

                updated.fit_gate = result
                updated.fit_gate_history.append(result)
                self._save_item(updated)
                outcomes.append(
                    ApplicationLoopFitGateOutcome(
                        loop_id=loop_id,
                        status="needs_jd" if result.evaluation_status == "needs_jd" else "evaluated",
                        result=result,
                        loop_item=updated,
                    )
                )
            except (KeyError, InvalidApplicationLoopTransition, RuntimeError, ValueError) as exc:
                outcomes.append(
                    ApplicationLoopFitGateOutcome(
                        loop_id=loop_id,
                        status="error",
                        error=str(exc),
                    )
                )

        return ApplicationLoopFitGateResponse(
            summary=self._summarize_fit_gate(outcomes),
            outcomes=outcomes,
        )

    def override_fit_gate(
        self,
        loop_id: str,
        payload: ApplicationLoopFitOverrideRequest,
    ) -> ApplicationLoopItem:
        item = self.get_item(loop_id)
        if item.fit_gate is None or item.fit_gate.evaluation_status != "complete":
            raise InvalidApplicationLoopTransition("Run Fit Gate with a complete JD before overriding its decision.")
        if item.state not in {"fit_checked", "skipped"}:
            raise InvalidApplicationLoopTransition(
                f"A Fit Gate decision cannot be overridden from '{item.state}'."
            )

        updated = item.model_copy(deep=True)
        target_state: ApplicationLoopState = "skipped" if payload.decision == "skip" else "fit_checked"
        if item.state != target_state:
            updated = self.transition(
                item,
                ApplicationLoopTransitionRequest(
                    target_state=target_state,
                    actor="human",
                    note=payload.note,
                ),
            )
        else:
            updated.updated_at = self._now()

        overridden = item.fit_gate.model_copy(deep=True)
        overridden.original_decision = item.fit_gate.original_decision or item.fit_gate.decision
        overridden.decision = payload.decision
        overridden.overridden = True
        overridden.override_note = payload.note.strip()
        overridden.evaluated_at = self._now()
        updated.fit_gate = overridden
        updated.fit_gate_history.append(overridden)
        self._save_item(updated)
        return updated

    def update_jd(self, loop_id: str, payload: ApplicationLoopJDUpdateRequest) -> ApplicationLoopItem:
        item = self.get_item(loop_id)
        if item.state != "imported":
            raise InvalidApplicationLoopTransition("The JD can be replaced only before Fit Gate completes.")

        updated = item.model_copy(deep=True)
        updated.jd_text = payload.jd_text.strip()
        updated.fit_gate = None
        updated.updated_at = self._now()
        self._save_item(updated)
        return updated

    def create_tailoring_draft(
        self,
        loop_id: str,
        payload: ApplicationLoopTailoringDraftRequest,
    ) -> ApplicationLoopTailoringDraftResponse:
        item = self.get_item(loop_id)
        if self.tailoring_review is None:
            raise RuntimeError("Tailoring review service is not configured.")
        if item.state not in {"fit_checked", "draft_ready", "approved_for_apply"}:
            raise InvalidApplicationLoopTransition(
                f"A tailoring draft cannot be created from '{item.state}'."
            )
        if item.state == "fit_checked":
            if item.fit_gate is None or item.fit_gate.evaluation_status != "complete":
                raise InvalidApplicationLoopTransition("Complete Fit Gate before tailoring this job.")
            if item.fit_gate.decision != "apply":
                raise InvalidApplicationLoopTransition(
                    "Change the Fit Gate decision to apply before spending a tailoring call."
                )
        elif item.tailoring_draft is None:
            raise InvalidApplicationLoopTransition("The current application has no draft to revise.")

        revision_reason = payload.revision_reason.strip()
        is_revision = item.state in {"draft_ready", "approved_for_apply"}
        if is_revision and len(revision_reason) < 3:
            raise InvalidApplicationLoopTransition(
                "Record what should change before regenerating the resume."
            )

        preference_memory = None
        if payload.preference_memory_fingerprint:
            candidate_memory = self.tailoring_memory(
                item.role,
                exclude_loop_id=item.loop_id,
            )
            if (
                candidate_memory.available
                and candidate_memory.fingerprint == payload.preference_memory_fingerprint
            ):
                preference_memory = candidate_memory

        draft = self.tailoring_review.create_draft(
            TailoringDraftRequest(
                url=item.job_url,
                page_title=f"{item.role} at {item.company}",
                page_text=item.jd_text,
                company=item.company,
                role=item.role,
                source=item.source,
                render_pdf=False,
                tailoring_preferences=payload.preferences,
            )
        )

        if is_revision:
            revision_requested = self.transition(
                item,
                ApplicationLoopTransitionRequest(
                    target_state="revision_requested",
                    actor="human",
                    note=revision_reason,
                ),
            )
            updated = self.transition(
                revision_requested,
                ApplicationLoopTransitionRequest(
                    target_state="draft_ready",
                    actor="agent",
                    note=f"Tailoring draft v{len(item.tailoring_history) + 1} generated for review.",
                ),
            )
        else:
            updated = self.transition(
                item,
                ApplicationLoopTransitionRequest(
                    target_state="draft_ready",
                    actor="agent",
                    note=(
                        "Initial tailoring draft generated for review using learned defaults "
                        f"from {preference_memory.approved_sample_count} approved similar-role "
                        "application(s)."
                        if preference_memory is not None
                        else "Initial tailoring draft generated for review."
                    ),
                ),
            )

        reference = ApplicationLoopTailoringDraftRef(
            draft_id=draft.draft_id,
            version=len(item.tailoring_history) + 1,
            base_score=draft.base_score,
            tailored_score=draft.tailored_score,
            revision_reason=revision_reason,
            preferences=draft.preferences,
            preference_memory_fingerprint=(
                preference_memory.fingerprint if preference_memory is not None else ""
            ),
            preference_memory_role_family=(
                preference_memory.role_family if preference_memory is not None else ""
            ),
            preference_memory_source_count=(
                preference_memory.approved_sample_count if preference_memory is not None else 0
            ),
            engine=draft.engine,
            model=draft.model,
            llm_usage=draft.llm_usage,
            claude_call_consumed=draft.claude_call_consumed,
            created_at=self._now(),
        )
        updated.tailoring_draft = reference
        updated.tailoring_history.append(reference)
        updated.tailoring_approval = None
        updated.export_handoff = None
        updated.ats_assist = None
        self._save_item(updated)
        return ApplicationLoopTailoringDraftResponse(loop_item=updated, draft=draft)

    def get_tailoring_draft(self, loop_id: str) -> ApplicationLoopTailoringDraftResponse:
        item = self.get_item(loop_id)
        if self.tailoring_review is None:
            raise RuntimeError("Tailoring review service is not configured.")
        if item.tailoring_draft is None:
            raise InvalidApplicationLoopTransition("This application does not have a tailoring draft yet.")
        draft = self.tailoring_review.get_draft(item.tailoring_draft.draft_id)
        if item.tailoring_approval and item.tailoring_approval.draft_id == draft.draft_id:
            approved_preview = self.tailoring_review.render_preview(item.tailoring_approval.review)
            draft = draft.model_copy(
                update={
                    "resume_preview_html": approved_preview.resume_preview_html,
                    "message": "Approved tailoring review reopened without generating files.",
                }
            )
        return ApplicationLoopTailoringDraftResponse(loop_item=item, draft=draft)

    def render_tailoring_preview(
        self,
        loop_id: str,
        payload: TailoringReviewSelection,
    ) -> TailoringPreviewRenderResponse:
        item = self.get_item(loop_id)
        if self.tailoring_review is None:
            raise RuntimeError("Tailoring review service is not configured.")
        self._validate_current_draft(item, payload.draft_id)
        return self.tailoring_review.render_preview(payload)

    def approve_tailoring_draft(
        self,
        loop_id: str,
        payload: ApplicationLoopTailoringApproveRequest,
    ) -> ApplicationLoopTailoringApproveResponse:
        item = self.get_item(loop_id)
        if self.tailoring_review is None:
            raise RuntimeError("Tailoring review service is not configured.")
        if item.state != "draft_ready":
            raise InvalidApplicationLoopTransition(
                f"A tailoring draft cannot be approved from '{item.state}'."
            )
        self._validate_current_draft(item, payload.draft_id)
        review = TailoringReviewSelection.model_validate(
            payload.model_dump(exclude={"approval_note"})
        )
        preview = self.tailoring_review.approve_draft(review)
        updated = self.transition(
            item,
            ApplicationLoopTransitionRequest(
                target_state="approved_for_apply",
                actor="human",
                note=payload.approval_note,
            ),
        )
        updated.tailoring_approval = ApplicationLoopTailoringApproval(
            draft_id=payload.draft_id,
            review=review,
            note=payload.approval_note.strip(),
            approved_at=self._now(),
        )
        updated.export_handoff = None
        updated.ats_assist = None
        self._save_item(updated)
        return ApplicationLoopTailoringApproveResponse(
            loop_item=updated,
            draft_id=payload.draft_id,
            resume_preview_html=preview.resume_preview_html,
            message=preview.message,
        )

    def export_approved_tailoring(
        self,
        loop_id: str,
        payload: ApplicationLoopTailoringExportRequest,
    ) -> ApplicationLoopTailoringExportResponse:
        item = self.get_item(loop_id)
        if self.tailoring_review is None:
            raise RuntimeError("Tailoring review service is not configured.")
        if not payload.human_confirmed_export:
            raise InvalidApplicationLoopTransition(
                "Export requires an explicit human confirmation after reviewing the approved resume."
            )
        if item.state not in {"approved_for_apply", "ats_opened"}:
            raise InvalidApplicationLoopTransition(
                f"Resume files cannot be generated from '{item.state}'. Approve the draft first."
            )
        if item.tailoring_draft is None or item.tailoring_approval is None:
            raise InvalidApplicationLoopTransition("This application does not have an approved tailoring review.")
        if item.tailoring_approval.draft_id != item.tailoring_draft.draft_id:
            raise InvalidApplicationLoopTransition(
                "The approved review does not match the current tailoring draft. Review it again before export."
            )

        finalized = self.tailoring_review.finalize(
            TailoringFinalizeRequest(
                **item.tailoring_approval.review.model_dump(),
                output_root_override=payload.output_root_override.strip(),
                render_pdf=payload.render_pdf,
            )
        )
        version = (item.export_handoff.version if item.export_handoff else 0) + 1
        handoff = ApplicationLoopExportHandoff(
            version=version,
            draft_id=item.tailoring_draft.draft_id,
            exported_at=self._now(),
            output_root_override=payload.output_root_override.strip(),
            render_pdf_requested=payload.render_pdf,
            quality_passed=finalized.quality_passed,
            quality_checks=finalized.quality_checks,
            docx_ready=finalized.docx_ready,
            pdf_ready=finalized.pdf_ready,
            pdf_error=finalized.pdf_error,
            docx_download_path=f"/application-loop/items/{loop_id}/tailoring/download/docx",
            pdf_download_path=(
                f"/application-loop/items/{loop_id}/tailoring/download/pdf"
                if finalized.pdf_ready
                else ""
            ),
            prepared_resume_docx_path=finalized.prepared_resume_docx_path,
            prepared_resume_pdf_path=finalized.prepared_resume_pdf_path,
            packet_folder_path=finalized.packet_folder_path,
            prepared_apply_plan_path=finalized.prepared_apply_plan_path,
            jd_path=finalized.jd_path,
            cover_letter_path=finalized.cover_letter_path,
            files_written=finalized.files_written,
        )
        updated = item.model_copy(deep=True)
        updated.export_handoff = handoff
        updated.ats_assist = None
        updated.updated_at = handoff.exported_at
        updated.history.append(
            ApplicationLoopEvent(
                from_state=item.state,
                to_state=item.state,
                actor="human",
                note=(
                    f"Export handoff v{version} generated from approved draft "
                    f"{item.tailoring_draft.version}."
                ),
                occurred_at=handoff.exported_at,
            )
        )
        self._save_item(updated)

        if payload.render_pdf and not handoff.pdf_ready:
            message = "DOCX is ready. PDF rendering needs attention before the PDF can be downloaded."
        elif handoff.quality_passed:
            message = "Approved resume files are ready for download and ATS handoff."
        else:
            message = "Resume files were generated, but the quality checks need review before applying."
        return ApplicationLoopTailoringExportResponse(
            loop_item=updated,
            handoff=handoff,
            message=message,
        )

    def get_tailoring_export(self, loop_id: str) -> ApplicationLoopTailoringExportResponse:
        item = self.get_item(loop_id)
        if item.export_handoff is None:
            raise InvalidApplicationLoopTransition("This application does not have an export handoff yet.")
        return ApplicationLoopTailoringExportResponse(
            loop_item=item,
            handoff=item.export_handoff,
            message="Existing export handoff reopened without regenerating files.",
        )

    def download_tailoring_export(self, loop_id: str, file_format: str) -> Path:
        item = self.get_item(loop_id)
        if item.export_handoff is None:
            raise FileNotFoundError("This application does not have exported resume files.")
        handoff = item.export_handoff
        if file_format == "docx" and handoff.docx_ready:
            path = Path(handoff.prepared_resume_docx_path)
        elif file_format == "pdf" and handoff.pdf_ready:
            path = Path(handoff.prepared_resume_pdf_path)
        elif file_format not in {"docx", "pdf"}:
            raise FileNotFoundError(f"Unsupported resume format: {file_format}")
        else:
            raise FileNotFoundError(f"{file_format.upper()} file is not available.")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"{file_format.upper()} export file no longer exists.")
        return path

    def arm_ats_assist(
        self,
        loop_id: str,
        payload: ApplicationLoopATSArmRequest,
    ) -> ApplicationLoopATSAssistResponse:
        item = self.get_item(loop_id)
        if self.autofill_autopilot is None:
            raise RuntimeError("ATS Apply Assist is not configured.")
        if item.state not in {"approved_for_apply", "ats_opened"}:
            raise InvalidApplicationLoopTransition(
                f"ATS Apply Assist cannot open from '{item.state}'. Approve and export the resume first."
            )
        handoff = item.export_handoff
        if handoff is None or not handoff.docx_ready:
            raise InvalidApplicationLoopTransition("Generate the approved resume export before opening the ATS.")
        if not handoff.prepared_apply_plan_path or not Path(handoff.prepared_apply_plan_path).is_file():
            raise InvalidApplicationLoopTransition("The approved export is missing its ATS apply plan. Regenerate it first.")
        if not handoff.quality_passed and len(payload.quality_review_note.strip()) < 3:
            raise InvalidApplicationLoopTransition(
                "The export quality checks need a short human review note before ATS handoff."
            )

        target_url = item.canonical_job_url or item.job_url
        if not target_url:
            raise InvalidApplicationLoopTransition("This application does not have a canonical ATS URL.")
        preferred_format = "pdf" if handoff.pdf_ready and Path(handoff.prepared_resume_pdf_path).is_file() else "docx"
        preferred_path = (
            handoff.prepared_resume_pdf_path if preferred_format == "pdf" else handoff.prepared_resume_docx_path
        )
        if not preferred_path or not Path(preferred_path).is_file():
            raise InvalidApplicationLoopTransition("The approved resume file is no longer available. Regenerate it first.")

        armed = self.autofill_autopilot.arm(
            AutofillAutopilotArmRequest(
                loop_id=loop_id,
                url=target_url,
                apply_plan_path=handoff.prepared_apply_plan_path,
                overwrite=False,
                open_browser=False,
                expires_minutes=payload.expires_minutes,
            )
        )
        if not armed.armed:
            raise RuntimeError(armed.message or "ATS Apply Assist could not be armed.")

        version = (item.ats_assist.version if item.ats_assist else 0) + 1
        assist = ApplicationLoopATSAssist(
            version=version,
            task_id=armed.task_id,
            status="armed",
            target_url=armed.target_url,
            apply_plan_path=handoff.prepared_apply_plan_path,
            preferred_resume_path=preferred_path,
            preferred_resume_format=preferred_format,
            opened_at=self._now(),
            expires_at=armed.expires_at,
            quality_review_note=payload.quality_review_note.strip(),
        )
        quality_note = (
            f" Quality review: {payload.quality_review_note.strip()}"
            if not handoff.quality_passed
            else ""
        )
        if item.state == "approved_for_apply":
            updated = self.transition(
                item,
                ApplicationLoopTransitionRequest(
                    target_state="ats_opened",
                    actor="human",
                    note=(
                        "ATS Apply Assist armed for safe fields only; resume upload review and final submit remain manual."
                        f"{quality_note}"
                    ),
                ),
            )
        else:
            updated = item.model_copy(deep=True)
            updated.updated_at = assist.opened_at
            updated.history.append(
                ApplicationLoopEvent(
                    from_state=item.state,
                    to_state=item.state,
                    actor="human",
                    note=f"ATS Apply Assist re-armed as handoff v{version}.{quality_note}",
                    occurred_at=assist.opened_at,
                )
            )
        updated.ats_assist = assist
        self._save_item(updated)
        return ApplicationLoopATSAssistResponse(
            loop_item=updated,
            assist=assist,
            message="Application opened for guarded prefill. Review every field, upload the approved resume manually, and submit yourself.",
        )

    def sync_ats_assist(self, loop_id: str) -> ApplicationLoopATSAssistResponse:
        item = self.get_item(loop_id)
        if self.autofill_autopilot is None:
            raise RuntimeError("ATS Apply Assist is not configured.")
        if item.ats_assist is None:
            raise InvalidApplicationLoopTransition("This application does not have an ATS Apply Assist handoff.")

        task = self.autofill_autopilot.get_task(item.ats_assist.task_id)
        result = dict(task.get("last_result") or {}) if task else {}
        if not result:
            message = (
                "ATS Apply Assist is armed and waiting for Third Eye to report the application form."
                if item.ats_assist.status == "armed"
                else "The latest ATS review result is shown; Third Eye has not reported a newer form result."
            )
            return ApplicationLoopATSAssistResponse(
                loop_item=item,
                assist=item.ats_assist,
                message=message,
            )

        review_items: list[ApplicationLoopATSReviewItem] = []
        seen: set[str] = set()
        for raw in result.get("results") or []:
            action = str(raw.get("action") or "")
            sensitive = bool(raw.get("sensitive"))
            if not sensitive and action not in {"manual_upload", "manual_review", "skip_sensitive", "skip_unknown"}:
                continue
            key = str(raw.get("field_id") or raw.get("label") or action)
            if key in seen:
                continue
            seen.add(key)
            review_items.append(
                ApplicationLoopATSReviewItem(
                    field_id=str(raw.get("field_id") or ""),
                    label=str(raw.get("label") or "Unrecognized application question"),
                    action=action,
                    reason=str(raw.get("reason") or "Review this field manually."),
                    sensitive=sensitive,
                    source=str(raw.get("source") or ""),
                )
            )

        updated = item.model_copy(deep=True)
        terminal_outcome = updated.ats_assist.status in {"technical_issue", "submitted_confirmed"}
        if not terminal_outcome:
            updated.ats_assist.status = "review_required" if review_items else "safe_fields_filled"
        updated.ats_assist.last_result_at = str(task.get("last_result_at") or self._now())
        updated.ats_assist.filled_count = max(0, int(result.get("filled_count") or 0))
        updated.ats_assist.total_fields = max(0, int(result.get("total_fields") or 0))
        updated.ats_assist.fillable_count = max(0, int(result.get("fillable_count") or 0))
        updated.ats_assist.manual_count = max(0, int(result.get("manual_count") or 0))
        updated.ats_assist.skipped_count = max(0, int(result.get("skipped_count") or 0))
        updated.ats_assist.review_items = review_items
        updated.updated_at = updated.ats_assist.last_result_at
        self._save_item(updated)
        if terminal_outcome:
            message = "The latest field report was recorded without changing the human-confirmed ATS outcome."
        else:
            message = (
                f"Safe prefill reported. Review {len(review_items)} manual or protected field"
                f"{'s' if len(review_items) != 1 else ''} before submitting."
                if review_items
                else "Safe prefill reported. Review the complete form and upload the approved resume before submitting."
            )
        return ApplicationLoopATSAssistResponse(loop_item=updated, assist=updated.ats_assist, message=message)

    def record_ats_outcome(
        self,
        loop_id: str,
        payload: ApplicationLoopATSOutcomeRequest,
    ) -> ApplicationLoopATSOutcomeResponse:
        item = self.get_item(loop_id)
        if item.state != "ats_opened" or item.ats_assist is None:
            raise InvalidApplicationLoopTransition("Open ATS Apply Assist before recording an application outcome.")

        occurred_at = self._now()
        if payload.outcome == "submitted_confirmed":
            if not payload.human_confirmed_submission:
                raise InvalidApplicationLoopTransition(
                    "Manual submission confirmation is required before marking this application submitted."
                )
            updated = self.transition(
                item,
                ApplicationLoopTransitionRequest(
                    target_state="submitted_confirmed",
                    actor="human",
                    note=payload.note,
                    human_confirmed_submission=True,
                ),
            )
            updated.ats_assist.status = "submitted_confirmed"
            status = "Applied"
            message = "Manual submission confirmed. The Applied row is ready for the Sheets logging loop."
        else:
            updated = item.model_copy(deep=True)
            updated.updated_at = occurred_at
            updated.ats_assist.status = "technical_issue"
            updated.ats_assist.technical_issue_note = payload.note.strip()
            updated.history.append(
                ApplicationLoopEvent(
                    from_state=item.state,
                    to_state=item.state,
                    actor="human",
                    note=f"ATS technical issue recorded: {payload.note.strip()}",
                    occurred_at=occurred_at,
                )
            )
            status = "Not Yet Applied Due to Technical Issue"
            message = "Portal failure recorded. A technical-issue row is ready for the Sheets logging loop; this job was not marked Applied."

        updated.ats_assist.sheets_status_proposal = status
        sheet_row = self._sheet_row_proposal(updated, status=status, occurred_at=occurred_at)
        self._save_item(updated)
        return ApplicationLoopATSOutcomeResponse(
            loop_item=updated,
            assist=updated.ats_assist,
            sheet_row_proposal=sheet_row,
            message=message,
        )

    def propose_sheet_row(self, loop_id: str, *, status: str) -> dict[str, str]:
        return self._sheet_row_proposal(
            self.get_item(loop_id),
            status=status,
            occurred_at=self._now(),
        )

    def prepare_recruiter_outreach_batch(
        self,
        payload: ApplicationLoopOutreachBatchRequest,
    ) -> ApplicationLoopOutreachBatchResponse:
        if self.recruiter_outreach is None:
            raise RuntimeError("Recruiter outreach batch service is not configured.")

        generated_at = self._now()
        loop_ids = list(dict.fromkeys(loop_id.strip() for loop_id in payload.loop_ids if loop_id.strip()))
        outcomes: list[ApplicationLoopOutreachBatchOutcome] = []
        pending: list[tuple[ApplicationLoopItem, dict[str, Any], str]] = []

        for loop_id in loop_ids:
            try:
                item = self.get_item(loop_id)
                if item.state not in {"submitted_confirmed", "sheet_logged", "recruiter_note_ready"}:
                    raise InvalidApplicationLoopTransition(
                        "Recruiter outreach can be prepared only after manual application submission."
                    )
                job = self._outreach_job(item)
                cache_key = self.recruiter_outreach.cache_key(job)
                if (
                    not payload.force_refresh
                    and item.recruiter_outreach is not None
                    and item.recruiter_outreach.cache_key == cache_key
                ):
                    outcomes.append(
                        ApplicationLoopOutreachBatchOutcome(
                            loop_id=loop_id,
                            company=item.company,
                            role=item.role,
                            status="cached",
                            outreach=item.recruiter_outreach,
                            loop_item=item,
                        )
                    )
                    continue
                pending.append((item, job, cache_key))
            except (KeyError, InvalidApplicationLoopTransition, ValueError) as exc:
                outcomes.append(
                    ApplicationLoopOutreachBatchOutcome(
                        loop_id=loop_id,
                        status="error",
                        error=str(exc),
                    )
                )

        batch_result = self.recruiter_outreach.draft_batch(
            [job for _, job, _ in pending],
            use_llm=payload.use_llm,
        )
        notes = batch_result.get("notes") or {}
        for item, job, cache_key in pending:
            try:
                note = str(notes.get(item.loop_id) or "").strip()
                if not note:
                    raise ValueError("No grounded recruiter connection note was generated.")
                if len(note) > 300:
                    raise ValueError("The generated recruiter connection note exceeds 300 characters.")

                version = (item.recruiter_outreach.version if item.recruiter_outreach else 0) + 1
                outreach = ApplicationLoopRecruiterOutreach(
                    version=version,
                    linkedin_search_url=RecruiterService.linkedin_search_url(item.company, item.role),
                    connection_note=note,
                    engine=str(batch_result.get("engine") or "deterministic_fallback"),
                    model=str(batch_result.get("model") or ""),
                    cache_key=cache_key,
                    llm_usage=dict(batch_result.get("llm_usage") or {}),
                    claude_call_consumed=bool(batch_result.get("claude_call_consumed")),
                    generated_at=generated_at,
                )
                if item.state in {"submitted_confirmed", "sheet_logged"}:
                    updated = self.transition(
                        item,
                        ApplicationLoopTransitionRequest(
                            target_state="recruiter_note_ready",
                            actor="agent",
                            note=f"Recruiter outreach note v{version} prepared for manual review and sending.",
                        ),
                    )
                else:
                    updated = item.model_copy(deep=True)
                    updated.updated_at = generated_at
                    updated.history.append(
                        ApplicationLoopEvent(
                            from_state=item.state,
                            to_state=item.state,
                            actor="agent",
                            note=f"Recruiter outreach note v{version} regenerated for manual review.",
                            occurred_at=generated_at,
                        )
                    )
                updated.recruiter_outreach = outreach
                self._save_item(updated)
                outcomes.append(
                    ApplicationLoopOutreachBatchOutcome(
                        loop_id=item.loop_id,
                        company=item.company,
                        role=item.role,
                        status="ready",
                        outreach=outreach,
                        loop_item=updated,
                    )
                )
            except (KeyError, InvalidApplicationLoopTransition, ValueError) as exc:
                outcomes.append(
                    ApplicationLoopOutreachBatchOutcome(
                        loop_id=item.loop_id,
                        company=item.company,
                        role=item.role,
                        status="error",
                        error=str(exc),
                    )
                )

        position = {loop_id: index for index, loop_id in enumerate(loop_ids)}
        outcomes.sort(key=lambda outcome: position.get(outcome.loop_id, len(position)))
        grouped: dict[str, list[ApplicationLoopOutreachBatchOutcome]] = {}
        for outcome in outcomes:
            company = outcome.company or "Unavailable"
            grouped.setdefault(company, []).append(outcome)
        groups = [
            ApplicationLoopOutreachCompanyGroup(company=company, outcomes=company_outcomes)
            for company, company_outcomes in grouped.items()
        ]
        llm_calls = int(bool(pending and batch_result.get("claude_call_consumed")))
        return ApplicationLoopOutreachBatchResponse(
            generated_at=generated_at,
            summary=ApplicationLoopOutreachBatchSummary(
                requested=len(outcomes),
                companies=len(grouped),
                ready=sum(outcome.status == "ready" for outcome in outcomes),
                cached=sum(outcome.status == "cached" for outcome in outcomes),
                llm_calls=llm_calls,
                failed=sum(outcome.status == "error" for outcome in outcomes),
            ),
            groups=groups,
            outcomes=outcomes,
        )

    def update_recruiter_outreach(
        self,
        loop_id: str,
        payload: ApplicationLoopOutreachUpdateRequest,
    ) -> ApplicationLoopOutreachResponse:
        item = self.get_item(loop_id)
        if item.state != "recruiter_note_ready" or item.recruiter_outreach is None:
            raise InvalidApplicationLoopTransition(
                "Prepare a recruiter note before editing outreach details."
            )
        edited_at = self._now()
        updated = item.model_copy(deep=True)
        updated.recruiter_outreach.recruiter_name = payload.recruiter_name.strip()
        updated.recruiter_outreach.connection_note = " ".join(payload.connection_note.split())
        updated.recruiter_outreach.edited_at = edited_at
        updated.updated_at = edited_at
        updated.history.append(
            ApplicationLoopEvent(
                from_state=item.state,
                to_state=item.state,
                actor="human",
                note="Recruiter name or connection note edited before sending.",
                occurred_at=edited_at,
            )
        )
        self._save_item(updated)
        return ApplicationLoopOutreachResponse(
            loop_item=updated,
            outreach=updated.recruiter_outreach,
            message="Recruiter outreach note saved for manual sending.",
        )

    def mark_recruiter_outreach_sent(
        self,
        loop_id: str,
        payload: ApplicationLoopOutreachSentRequest,
    ) -> ApplicationLoopOutreachResponse:
        item = self.get_item(loop_id)
        if item.state != "recruiter_note_ready" or item.recruiter_outreach is None:
            raise InvalidApplicationLoopTransition(
                "A reviewed recruiter note must be ready before outreach can be marked sent."
            )
        if not payload.human_confirmed_sent:
            raise InvalidApplicationLoopTransition(
                "Explicit human confirmation is required before marking recruiter outreach sent."
            )
        updated = self.transition(
            item,
            ApplicationLoopTransitionRequest(
                target_state="outreach_done",
                actor="human",
                note=payload.note,
            ),
        )
        updated.recruiter_outreach.status = "sent"
        updated.recruiter_outreach.sent_at = updated.updated_at
        updated.recruiter_outreach.sent_note = payload.note.strip()
        self._save_item(updated)
        return ApplicationLoopOutreachResponse(
            loop_item=updated,
            outreach=updated.recruiter_outreach,
            message="Manual recruiter outreach recorded separately from the application submission.",
        )

    @staticmethod
    def _outreach_job(item: ApplicationLoopItem) -> dict[str, Any]:
        strengths = item.fit_gate.strengths if item.fit_gate else []
        return {
            "loop_id": item.loop_id,
            "company": item.company,
            "role": item.role,
            "jd_text": item.jd_text,
            "fit_strengths": strengths,
        }

    @staticmethod
    def _validate_current_draft(item: ApplicationLoopItem, draft_id: str) -> None:
        if item.tailoring_draft is None or item.tailoring_draft.draft_id != draft_id:
            raise InvalidApplicationLoopTransition(
                "The tailoring request does not match the current draft for this application."
            )

    def _evaluate_fit_gate(
        self,
        item: ApplicationLoopItem,
        *,
        use_llm: bool,
        force_refresh: bool,
    ) -> ApplicationLoopFitGateResult:
        evaluated_at = self._now()
        if len(item.jd_text.strip()) < 80:
            return ApplicationLoopFitGateResult(
                decision="maybe",
                evaluation_status="needs_jd",
                score=0,
                deterministic_score=0,
                deterministic_decision="pending",
                one_line_reason="Full job description is missing; add the JD before making an apply or skip decision.",
                gaps=["Full job description is not available."],
                suggested_actions=["Paste the complete JD and run Fit Gate again."],
                sponsorship_note="Sponsorship language cannot be verified without the JD.",
                seniority_note="Seniority requirements cannot be verified without the JD.",
                location_note="Location eligibility cannot be verified without the JD.",
                title_fit_note="The role title is available, but its actual scope needs the JD.",
                skills_fit_note="Required and preferred skills cannot be scored without the JD.",
                evaluated_at=evaluated_at,
            )

        if self.matcher is None:
            raise RuntimeError("Fit Gate matcher is not configured.")

        analysis = self.matcher.analyze(
            {
                "job_id": item.loop_id,
                "company": item.company,
                "title": item.role,
                "jd_text": item.jd_text,
                "discovered_url": item.job_url,
                "source": item.source,
            },
            use_llm=use_llm,
            force_refresh=force_refresh,
        )
        decision = self._fit_gate_decision(analysis)
        scoring_mode = str(analysis.get("scoring_mode") or "deterministic_fallback")
        cache_hit = bool(analysis.get("cache_hit"))
        used_llm = scoring_mode == "llm"

        return ApplicationLoopFitGateResult(
            decision=decision,
            score=self._coerce_score(analysis.get("score")),
            one_line_reason=str(analysis.get("one_line_reason") or "Fit Gate completed."),
            strengths=self._string_list(analysis.get("strengths")),
            gaps=self._string_list(analysis.get("gaps")),
            risks=self._string_list(analysis.get("risks")),
            suggested_actions=self._string_list(analysis.get("suggested_actions")),
            sponsorship_note=str(analysis.get("sponsorship_note") or "Sponsorship language needs review."),
            seniority_note=self._seniority_note(analysis),
            location_note=self._location_note(analysis),
            title_fit_note=self._title_fit_note(analysis),
            skills_fit_note=self._skills_fit_note(analysis),
            deterministic_score=self._coerce_score(
                analysis.get("deterministic_score", analysis.get("score"))
            ),
            deterministic_decision=str(analysis.get("quality_gate_decision") or ""),
            used_llm=used_llm,
            cache_hit=cache_hit,
            scoring_mode=scoring_mode,
            llm_provider=str(analysis.get("llm_provider") or ""),
            llm_model=str(analysis.get("llm_model") or ""),
            evaluated_at=evaluated_at,
        )

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
    def _summarize_fit_gate(
        outcomes: list[ApplicationLoopFitGateOutcome],
    ) -> ApplicationLoopFitGateSummary:
        complete_results = [
            outcome.result
            for outcome in outcomes
            if outcome.result is not None and outcome.result.evaluation_status == "complete"
        ]
        return ApplicationLoopFitGateSummary(
            requested=len(outcomes),
            evaluated=sum(outcome.status == "evaluated" for outcome in outcomes),
            cached=sum(
                outcome.status == "cached" or bool(outcome.result and outcome.result.cache_hit)
                for outcome in outcomes
            ),
            needs_jd=sum(outcome.status == "needs_jd" for outcome in outcomes),
            apply=sum(result.decision == "apply" for result in complete_results),
            maybe=sum(result.decision == "maybe" for result in complete_results),
            skip=sum(result.decision == "skip" for result in complete_results),
            llm_calls=sum(
                bool(
                    outcome.status == "evaluated"
                    and outcome.result
                    and outcome.result.used_llm
                    and not outcome.result.cache_hit
                )
                for outcome in outcomes
            ),
            failed=sum(outcome.status == "error" for outcome in outcomes),
        )

    def _save_item(self, item: ApplicationLoopItem) -> None:
        conn = get_db_connection()
        try:
            cursor = conn.execute(
                """
                UPDATE application_loop_items
                SET item_json = ?, updated_at = ?
                WHERE loop_id = ?
                """,
                (item.model_dump_json(), item.updated_at, item.loop_id),
            )
            conn.commit()
        finally:
            conn.close()
        if cursor.rowcount == 0:
            raise KeyError(f"Application loop item not found: {item.loop_id}")

    @staticmethod
    def _fit_gate_decision(analysis: dict[str, Any]) -> str:
        verdict = str(analysis.get("verdict") or "review")
        if verdict == "skip":
            return "skip"
        if verdict in {"strong_match", "good_match"} and bool(analysis.get("worth_applying")):
            return "apply"
        return "maybe"

    @classmethod
    def _seniority_note(cls, analysis: dict[str, Any]) -> str:
        risk = cls._first_matching(analysis.get("risks"), ("seniority", "experience requirement"))
        if risk:
            return risk
        years = analysis.get("years_required")
        if years is not None:
            try:
                formatted_years = f"{float(years):g}"
            except (TypeError, ValueError):
                formatted_years = str(years)
            return f"The posting appears to require {formatted_years} years of experience."
        return "No explicit seniority requirement above the configured junior target was found."

    @classmethod
    def _location_note(cls, analysis: dict[str, Any]) -> str:
        note = cls._first_matching(
            [*cls._string_list(analysis.get("risks")), *cls._string_list(analysis.get("strengths"))],
            ("location", "relocation", "remote"),
        )
        return note or "Location was not explicit enough to add a stronger eligibility claim."

    @classmethod
    def _title_fit_note(cls, analysis: dict[str, Any]) -> str:
        risk = cls._first_matching(analysis.get("risks"), ("title", "role famil"))
        if risk:
            return risk
        role_key = str(analysis.get("target_role_key") or "").strip()
        if role_key:
            return f"Title and duties align with the {role_key.replace('_', ' ')} target family."
        return "Title fit needs human review against the actual duties."

    @classmethod
    def _skills_fit_note(cls, analysis: dict[str, Any]) -> str:
        components = analysis.get("components") if isinstance(analysis.get("components"), dict) else {}
        required = components.get("required_skills")
        preferred = components.get("preferred_skills")
        gaps = cls._string_list(analysis.get("gaps"))
        if isinstance(required, (int, float)) and isinstance(preferred, (int, float)):
            note = f"Required skills score {int(required)}%; preferred skills score {int(preferred)}%."
            if gaps:
                note += f" Top gap: {gaps[0]}"
            return note
        strengths = cls._string_list(analysis.get("strengths"))
        if strengths:
            return strengths[0]
        return "Skills alignment needs human review."

    @classmethod
    def _first_matching(cls, values: Any, markers: tuple[str, ...]) -> str:
        for value in cls._string_list(values):
            lowered = value.casefold()
            if any(marker in lowered for marker in markers):
                return value
        return ""

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][:5]

    @staticmethod
    def _coerce_score(value: Any) -> int:
        try:
            return max(0, min(100, int(float(value))))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize_match_text(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip()).casefold()

    @staticmethod
    def _sheet_row_proposal(
        item: ApplicationLoopItem,
        *,
        status: str,
        occurred_at: str,
    ) -> dict[str, str]:
        link = item.canonical_job_url or item.job_url
        host = urlsplit(link).netloc.casefold()
        if "linkedin.com" in host:
            applied_using = "LinkedIn"
        elif "indeed.com" in host:
            applied_using = "Indeed"
        elif "ziprecruiter.com" in host:
            applied_using = "ZipRecruiter"
        elif "jobright.ai" in host:
            applied_using = "Jobright.ai"
        else:
            applied_using = "Company Website"
        try:
            date_applied = datetime.fromisoformat(occurred_at).astimezone().strftime("%m/%d/%Y")
        except ValueError:
            date_applied = datetime.now().strftime("%m/%d/%Y")
        return {
            "Date": date_applied,
            "Company Applied": item.company,
            "Role": item.role,
            "Salary Quoted while Applying": "N/A",
            "Job Posted On": item.source or "Unknown",
            "Applied Using": applied_using,
            "Status": status,
            "Link": link,
        }

    @staticmethod
    def _reached_state(item: ApplicationLoopItem, state: ApplicationLoopState) -> bool:
        return item.state == state or any(event.to_state == state for event in item.history)

    @classmethod
    def _transition_duration_samples(
        cls,
        items: list[ApplicationLoopItem],
        from_state: ApplicationLoopState,
        to_states: tuple[ApplicationLoopState, ...],
    ) -> list[float]:
        samples: list[float] = []
        for item in items:
            start = cls._first_state_timestamp(item, from_state)
            if start is None:
                continue
            end_candidates = [
                timestamp
                for state in to_states
                if (timestamp := cls._first_state_timestamp(item, state, after=start)) is not None
            ]
            if not end_candidates:
                continue
            minutes = (min(end_candidates) - start).total_seconds() / 60
            if minutes >= 0:
                samples.append(round(minutes, 3))
        return samples

    @classmethod
    def _first_state_timestamp(
        cls,
        item: ApplicationLoopItem,
        state: ApplicationLoopState,
        *,
        after: datetime | None = None,
    ) -> datetime | None:
        timestamps = [
            parsed
            for event in item.history
            if event.to_state == state
            and (parsed := cls._parse_metric_timestamp(event.occurred_at)) is not None
            and (after is None or parsed >= after)
        ]
        if state == "imported":
            created_at = cls._parse_metric_timestamp(item.created_at)
            if created_at is not None and (after is None or created_at >= after):
                timestamps.append(created_at)
        return min(timestamps) if timestamps else None

    @staticmethod
    def _parse_metric_timestamp(value: str) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _metrics_since(
        window: ApplicationLoopMetricsWindow,
        now: datetime,
    ) -> datetime | None:
        if window == "all":
            return None
        if window == "today":
            local_now = now.astimezone()
            return local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        days = 7 if window == "7d" else 30
        return now - timedelta(days=days)

    @staticmethod
    def _metrics_window_label(window: ApplicationLoopMetricsWindow) -> str:
        return {
            "today": "Today",
            "7d": "Last 7 days",
            "30d": "Last 30 days",
            "all": "All time",
        }[window]

    @staticmethod
    def _average(values: list[float]) -> float:
        return round(sum(values) / len(values), 1) if values else 0.0

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> float:
        return round((numerator / denominator) * 100, 1) if denominator else 0.0

    @staticmethod
    def _metric_reasons(values: Iterable[str]) -> list[ApplicationLoopMetricReason]:
        counts: Counter[str] = Counter()
        labels: dict[str, str] = {}
        for raw in values:
            reason = " ".join(str(raw or "").split()).strip()
            if not reason:
                continue
            key = reason.casefold()
            counts[key] += 1
            labels.setdefault(key, reason)
        return [
            ApplicationLoopMetricReason(reason=labels[key], count=count)
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], labels[item[0]].casefold()))[:5]
        ]

    def _tailoring_reference_preferences(
        self,
        reference: ApplicationLoopTailoringDraftRef,
    ) -> TailoringPreferences | None:
        if reference.preferences is not None:
            return reference.preferences.model_copy(deep=True)
        if self.tailoring_review is None:
            return None
        try:
            return self.tailoring_review.get_draft(reference.draft_id).preferences.model_copy(
                deep=True
            )
        except (HTTPException, KeyError, OSError, ValueError):
            return None

    @classmethod
    def _tailoring_role_family(cls, role: str) -> str:
        normalized = cls._normalize_match_text(role)
        if not normalized:
            return "general"
        if "computer vision" in normalized:
            return "computer_vision"
        if "business analyst" in normalized:
            return "business_analysis"
        if "analyst" in normalized or "business intelligence" in normalized:
            return "data_analytics"
        if "data engineer" in normalized or "analytics engineer" in normalized:
            return "data_engineering"
        if "data scientist" in normalized or "data science" in normalized:
            return "data_science"
        if "machine learning" in normalized or re.search(r"\bml\b", normalized):
            return "machine_learning"
        if any(
            marker in normalized
            for marker in ("ai engineer", "artificial intelligence", "generative ai", "llm")
        ):
            return "ai_engineering"
        if any(marker in normalized for marker in ("software engineer", "software developer")):
            return "software_engineering"
        return f"role:{normalized}"

    @staticmethod
    def _tailoring_role_family_label(role_family: str, role: str) -> str:
        labels = {
            "general": "General roles",
            "computer_vision": "Computer vision roles",
            "business_analysis": "Business analyst roles",
            "data_analytics": "Data analyst roles",
            "data_engineering": "Data engineering roles",
            "data_science": "Data science roles",
            "machine_learning": "Machine learning roles",
            "ai_engineering": "AI engineering roles",
            "software_engineering": "Software engineering roles",
        }
        return labels.get(role_family, f"{role.strip() or 'Similar'} roles")

    @staticmethod
    def _recent_mode(values: list[Any]) -> Any:
        counts = Counter(values)
        highest = max(counts.values())
        return next(value for value in values if counts[value] == highest)

    @staticmethod
    def _rounded_median(values: list[int]) -> int:
        return int(float(median(values)) + 0.5)

    @staticmethod
    def _dedupe_text(values: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for raw in values:
            value = " ".join(str(raw or "").split()).strip()
            key = value.casefold()
            if not value or key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result

    @staticmethod
    def _tailoring_memory_instruction_text(instructions: list[str]) -> str:
        if not instructions:
            return ""
        prefix = "Apply these past approved corrections when relevant: "
        selected: list[str] = []
        for instruction in instructions[:3]:
            candidate = prefix + "; ".join([*selected, instruction])
            if len(candidate) <= 600:
                selected.append(instruction)
                continue
            if not selected:
                selected.append(instruction[: 600 - len(prefix)].rstrip(" ,;:"))
            break
        return (prefix + "; ".join(selected))[:600]

    def _now(self) -> str:
        return self._clock().astimezone(UTC).isoformat()
