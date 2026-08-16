from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.application_loop import (
    ApplicationLoopCreateRequest,
    ApplicationLoopTransitionRequest,
)
from app.services.application_loop_service import (
    ApplicationLoopService,
    InvalidApplicationLoopTransition,
)


class AdvancingClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 16, 14, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(minutes=1)
        return value


def _new_loop() -> tuple[ApplicationLoopService, object]:
    service = ApplicationLoopService(clock=AdvancingClock())
    item = service.create(
        ApplicationLoopCreateRequest(
            lead_id="jobright_credit_one_17893342",
            company="Credit One Bank",
            role="Operations Data Analyst I",
            job_url="https://careers.creditonebank.com/jobs/17893342-operations-data-analyst",
            source="Jobright AI",
            actor="system",
        )
    )
    return service, item


def _move(service: ApplicationLoopService, item, target_state: str, **kwargs):
    return service.transition(
        item,
        ApplicationLoopTransitionRequest(target_state=target_state, **kwargs),
    )


def test_loop_records_the_happy_path_without_mutating_prior_versions() -> None:
    service, imported = _new_loop()

    fit_checked = _move(service, imported, "fit_checked", actor="agent")
    draft_ready = _move(service, fit_checked, "draft_ready", actor="agent")
    approved = _move(service, draft_ready, "approved_for_apply")
    ats_opened = _move(service, approved, "ats_opened", actor="system")
    submitted = _move(
        service,
        ats_opened,
        "submitted_confirmed",
        human_confirmed_submission=True,
        note="Application submitted manually in the company ATS.",
    )

    assert imported.state == "imported"
    assert imported.history[0].actor == "system"
    assert submitted.state == "submitted_confirmed"
    assert [event.to_state for event in submitted.history] == [
        "imported",
        "fit_checked",
        "draft_ready",
        "approved_for_apply",
        "ats_opened",
        "submitted_confirmed",
    ]
    assert submitted.history[-1].human_confirmed_submission is True
    assert submitted.updated_at > submitted.created_at


def test_submitted_confirmed_requires_explicit_human_confirmation() -> None:
    service, item = _new_loop()
    item = _move(service, item, "fit_checked", actor="agent")
    item = _move(service, item, "draft_ready", actor="agent")
    item = _move(service, item, "approved_for_apply")

    with pytest.raises(InvalidApplicationLoopTransition, match="human confirmation"):
        _move(service, item, "submitted_confirmed", actor="system", human_confirmed_submission=True)

    with pytest.raises(InvalidApplicationLoopTransition, match="human confirmation"):
        _move(service, item, "submitted_confirmed", actor="human")


def test_invalid_transition_explains_the_allowed_next_states() -> None:
    service, item = _new_loop()

    with pytest.raises(InvalidApplicationLoopTransition, match="fit_checked, skipped"):
        _move(service, item, "draft_ready", actor="agent")


def test_revision_loop_counts_each_requested_redraft() -> None:
    service, item = _new_loop()
    item = _move(service, item, "fit_checked", actor="agent")
    item = _move(service, item, "draft_ready", actor="agent")
    item = _move(service, item, "revision_requested", note="Add two grounded research bullets.")
    item = _move(service, item, "draft_ready", actor="agent")
    item = _move(service, item, "revision_requested", note="Strengthen the EREV analysis metrics.")

    assert item.state == "revision_requested"
    assert item.revision_count == 2
    assert item.history[-1].note == "Strengthen the EREV analysis metrics."


def test_only_a_human_can_restore_a_skipped_item() -> None:
    service, imported = _new_loop()
    skipped = _move(service, imported, "skipped", note="Role requires unrestricted work authorization.")

    assert service.allowed_next_states("skipped") == ("fit_checked",)
    with pytest.raises(InvalidApplicationLoopTransition, match="Only a human"):
        _move(service, skipped, "fit_checked", actor="agent", note="Agent changed its mind.")

    restored = _move(service, skipped, "fit_checked", note="Human reviewed the JD and overrode the false skip.")
    assert restored.state == "fit_checked"
    assert restored.history[-1].actor == "human"


def test_outreach_done_is_terminal() -> None:
    service, _ = _new_loop()
    assert service.allowed_next_states("outreach_done") == ()
