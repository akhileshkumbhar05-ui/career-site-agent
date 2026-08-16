from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import json
import re
import sqlite3
from typing import TYPE_CHECKING, Any
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
    ApplicationLoopFitGateOutcome,
    ApplicationLoopFitGateResponse,
    ApplicationLoopFitGateResult,
    ApplicationLoopFitGateRunRequest,
    ApplicationLoopFitGateSummary,
    ApplicationLoopFitOverrideRequest,
    ApplicationLoopItem,
    ApplicationLoopJDUpdateRequest,
    ApplicationLoopState,
    ApplicationLoopTransitionRequest,
)
from app.services.tracker_service import TrackerService

if TYPE_CHECKING:
    from app.services.llm_match_service import LLMMatchService


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
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self.matcher = matcher
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

    def _now(self) -> str:
        return self._clock().astimezone(UTC).isoformat()
