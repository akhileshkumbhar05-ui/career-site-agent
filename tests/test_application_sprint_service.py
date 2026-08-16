from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_application_sprint_service
from app.main import app
from app.schemas.application_loop import (
    ApplicationLoopBatchImportRequest,
    ApplicationLoopFitGateResult,
    ApplicationLoopRecruiterOutreach,
    ApplicationLoopTailoringDraftRef,
    ApplicationLoopSheetLoggedRequest,
)
from app.schemas.application_sprint import ApplicationSprintAddItemsRequest, ApplicationSprintCreateRequest
from app.services.application_loop_service import ApplicationLoopService, InvalidApplicationLoopTransition
from app.services.application_sprint_service import ApplicationSprintConflict, ApplicationSprintService


START = datetime(2026, 8, 16, 14, 0, tzinfo=UTC)


def _services(tmp_path, monkeypatch, count: int = 4):
    monkeypatch.setenv("CAREER_SITE_AGENT_DB_PATH", str(tmp_path / "sprints.db"))
    now = [START]
    loop_service = ApplicationLoopService(clock=lambda: now[0])
    batch = loop_service.import_batch(
        ApplicationLoopBatchImportRequest.model_validate(
            {
                "items": [
                    {
                        "company": f"Company {index}",
                        "role": f"Data Analyst {index}",
                        "job_url": f"https://careers.example.com/jobs/{index}",
                        "jd_text": "Analyze operational data with Python and SQL. " * 4,
                        "source": "Jobright AI",
                    }
                    for index in range(count)
                ]
            }
        )
    )
    loop_ids = [outcome.loop_item.loop_id for outcome in batch.outcomes]
    sprint_service = ApplicationSprintService(loop_service=loop_service, clock=lambda: now[0])
    return loop_service, sprint_service, loop_ids, now


def _set_state(loop_service: ApplicationLoopService, loop_id: str, state: str) -> None:
    item = loop_service.get_item(loop_id)
    item.state = state
    item.updated_at = START.isoformat()
    loop_service._save_item(item)


def test_sprint_derives_one_current_action_and_replacement_capacity(tmp_path, monkeypatch) -> None:
    loop_service, service, loop_ids, _ = _services(tmp_path, monkeypatch)
    sprint = service.create(
        ApplicationSprintCreateRequest(name="Monday sprint", target_count=3, loop_ids=loop_ids[:3])
    )

    assert sprint.current_loop_id == loop_ids[0]
    assert sprint.items[0].next_action.key == "run_fit_gate"
    assert sprint.stats.open_slots == 0

    _set_state(loop_service, loop_ids[0], "skipped")
    sprint = service.get(sprint.sprint_id)

    assert sprint.current_loop_id == loop_ids[1]
    assert sprint.items[0].next_action.key == "replace_job"
    assert sprint.stats.skipped_count == 1
    assert sprint.stats.open_slots == 1

    sprint = service.add_items(
        sprint.sprint_id,
        ApplicationSprintAddItemsRequest(loop_ids=[loop_ids[3]]),
    )
    assert sprint.stats.open_slots == 0
    assert sprint.stats.history_count == 4
    assert sprint.items[-1].position == 4


def test_sprint_pause_resume_excludes_paused_time(tmp_path, monkeypatch) -> None:
    _, service, loop_ids, now = _services(tmp_path, monkeypatch)
    sprint = service.create(ApplicationSprintCreateRequest(target_count=1, loop_ids=loop_ids[:1]))

    now[0] += timedelta(minutes=15)
    paused = service.pause(sprint.sprint_id)
    assert paused.status == "paused"
    assert paused.stats.elapsed_seconds == 15 * 60

    now[0] += timedelta(minutes=45)
    assert service.get(sprint.sprint_id).stats.elapsed_seconds == 15 * 60

    resumed = service.resume(sprint.sprint_id)
    now[0] += timedelta(minutes=5)
    resumed = service.get(resumed.sprint_id)
    assert resumed.status == "active"
    assert resumed.stats.elapsed_seconds == 20 * 60


def test_sprint_completes_at_confirmed_target_and_unlocks_outreach(tmp_path, monkeypatch) -> None:
    loop_service, service, loop_ids, _ = _services(tmp_path, monkeypatch)
    sprint = service.create(ApplicationSprintCreateRequest(target_count=2, loop_ids=loop_ids[:2]))

    _set_state(loop_service, loop_ids[0], "submitted_confirmed")
    partial = service.get(sprint.sprint_id)
    assert partial.status == "active"
    assert partial.stats.submitted_count == 1
    assert partial.outreach_unlocked is False
    assert partial.items[0].next_action.key == "log_sheets"

    _set_state(loop_service, loop_ids[1], "submitted_confirmed")
    completed = service.get(sprint.sprint_id)
    assert completed.status == "completed"
    assert completed.outreach_unlocked is True
    assert completed.ready_for_next_sprint is False
    assert completed.outreach_loop_ids == loop_ids[:2]

    for loop_id in loop_ids[:2]:
        _set_state(loop_service, loop_id, "outreach_done")
    closed = service.get(sprint.sprint_id)
    assert closed.ready_for_next_sprint is True

    next_sprint = service.create(ApplicationSprintCreateRequest(target_count=1, loop_ids=[loop_ids[2]]))
    assert next_sprint.status == "active"


def test_sprint_counts_sheets_revisions_and_actual_claude_calls(tmp_path, monkeypatch) -> None:
    loop_service, service, loop_ids, _ = _services(tmp_path, monkeypatch)
    first = loop_service.get_item(loop_ids[0])
    first.state = "sheet_logged"
    first.revision_count = 2
    first.fit_gate_history = [
        ApplicationLoopFitGateResult(
            decision="apply",
            score=88,
            one_line_reason="Strong match.",
            used_llm=True,
            cache_hit=False,
            evaluated_at=START.isoformat(),
        ),
        ApplicationLoopFitGateResult(
            decision="maybe",
            score=70,
            one_line_reason="Human override record.",
            used_llm=True,
            cache_hit=False,
            overridden=True,
            evaluated_at=START.isoformat(),
        ),
    ]
    first.tailoring_history = [
        ApplicationLoopTailoringDraftRef(
            draft_id="draft-1",
            version=1,
            base_score=78,
            tailored_score=88,
            claude_call_consumed=True,
            created_at=START.isoformat(),
        )
    ]
    first.recruiter_outreach = ApplicationLoopRecruiterOutreach(
        version=1,
        connection_note="A grounded recruiter note that fits within LinkedIn limits.",
        linkedin_search_url="https://linkedin.com/search/results/people/",
        generated_at=START.isoformat(),
        model="claude-sonnet",
        claude_call_consumed=True,
    )
    loop_service._save_item(first)

    second = loop_service.get_item(loop_ids[1])
    second.state = "submitted_confirmed"
    second.recruiter_outreach = first.recruiter_outreach.model_copy(deep=True)
    loop_service._save_item(second)

    sprint = service.create(ApplicationSprintCreateRequest(target_count=2, loop_ids=loop_ids[:2]))
    assert sprint.stats.sheet_logged_count == 1
    assert sprint.stats.revision_count == 2
    assert sprint.stats.claude_calls == 3


def test_sprint_rejects_overfill_and_second_active_sprint(tmp_path, monkeypatch) -> None:
    _, service, loop_ids, _ = _services(tmp_path, monkeypatch)
    sprint = service.create(ApplicationSprintCreateRequest(target_count=2, loop_ids=loop_ids[:2]))

    try:
        service.create(ApplicationSprintCreateRequest(target_count=1, loop_ids=[loop_ids[2]]))
        raise AssertionError("Expected active sprint conflict")
    except ApplicationSprintConflict:
        pass

    try:
        service.add_items(sprint.sprint_id, ApplicationSprintAddItemsRequest(loop_ids=[loop_ids[2]]))
        raise AssertionError("Expected sprint capacity conflict")
    except ApplicationSprintConflict:
        pass


def test_sheet_logged_transition_requires_confirmed_submission_and_persists(tmp_path, monkeypatch) -> None:
    loop_service, _, loop_ids, _ = _services(tmp_path, monkeypatch)
    _set_state(loop_service, loop_ids[0], "submitted_confirmed")

    with pytest.raises(InvalidApplicationLoopTransition):
        loop_service.mark_sheet_logged(
            loop_ids[0],
            ApplicationLoopSheetLoggedRequest(note="No successful Sheets response was received."),
        )

    updated = loop_service.mark_sheet_logged(
        loop_ids[0],
        ApplicationLoopSheetLoggedRequest(
            note="Google Sheets row created after manual submission confirmation.",
            sheet_write_succeeded=True,
        ),
    )

    assert updated.state == "sheet_logged"
    assert loop_service.get_item(loop_ids[0]).state == "sheet_logged"
    assert updated.history[-1].actor == "human"
    assert updated.history[-1].to_state == "sheet_logged"

def test_sprint_api_is_typed_and_exposes_current_sprint(tmp_path, monkeypatch) -> None:
    _, service, loop_ids, _ = _services(tmp_path, monkeypatch)
    app.dependency_overrides[get_application_sprint_service] = lambda: service
    try:
        client = TestClient(app)
        created = client.post(
            "/application-sprints",
            json={"name": "API sprint", "target_count": 2, "loop_ids": loop_ids[:2]},
        )
        current = client.get("/application-sprints/current")
        invalid = client.post(
            "/application-sprints",
            json={"name": "Too many", "target_count": 1, "loop_ids": loop_ids[:2]},
        )
    finally:
        app.dependency_overrides.clear()

    assert created.status_code == 200
    assert created.json()["stats"]["target_count"] == 2
    assert current.status_code == 200
    assert current.json()["sprint_id"] == created.json()["sprint_id"]
    assert invalid.status_code == 422
