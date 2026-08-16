from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.application_loop import (
    ApplicationLoopCreateRequest,
    ApplicationLoopEvent,
    ApplicationLoopItem,
    ApplicationLoopState,
    ApplicationLoopTransitionRequest,
)


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

    def _now(self) -> str:
        return self._clock().astimezone(UTC).isoformat()
