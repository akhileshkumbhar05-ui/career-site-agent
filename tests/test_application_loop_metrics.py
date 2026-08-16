from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.dependencies import get_application_loop_service
from app.main import app
from app.schemas.application_loop import (
    ApplicationLoopATSAssist,
    ApplicationLoopBatchImportRequest,
    ApplicationLoopEvent,
    ApplicationLoopTailoringDraftRef,
)
from app.services.application_loop_service import ApplicationLoopService


NOW = datetime(2026, 8, 16, 18, 0, tzinfo=UTC)


def _service(tmp_path, monkeypatch) -> tuple[ApplicationLoopService, list[str]]:
    monkeypatch.setenv("CAREER_SITE_AGENT_DB_PATH", str(tmp_path / "metrics.db"))
    service = ApplicationLoopService(clock=lambda: NOW)
    imported = service.import_batch(
        ApplicationLoopBatchImportRequest.model_validate(
            {
                "items": [
                    {
                        "company": company,
                        "role": role,
                        "job_url": f"https://careers.example.com/jobs/{index}",
                        "jd_text": "Analyze data with Python and SQL. " * 5,
                    }
                    for index, (company, role) in enumerate(
                        [
                            ("Northwind Analytics", "Operations Data Analyst"),
                            ("Contoso Health", "Healthcare Data Scientist"),
                            ("Fabrikam Energy", "Energy Reporting Analyst"),
                            ("Old Example", "Old Data Analyst"),
                        ]
                    )
                ]
            }
        )
    )
    loop_ids = [outcome.loop_item.loop_id for outcome in imported.outcomes]
    _seed_histories(service, loop_ids)
    return service, loop_ids


def _event(state: str, occurred_at: str, note: str = "") -> ApplicationLoopEvent:
    return ApplicationLoopEvent(
        to_state=state,
        actor="human" if state in {"approved_for_apply", "submitted_confirmed", "sheet_logged", "outreach_done"} else "agent",
        note=note,
        occurred_at=occurred_at,
        human_confirmed_submission=state == "submitted_confirmed",
    )


def _seed_histories(service: ApplicationLoopService, loop_ids: list[str]) -> None:
    happy = service.get_item(loop_ids[0])
    happy.created_at = "2026-08-15T10:00:00+00:00"
    happy.updated_at = "2026-08-15T12:30:00+00:00"
    happy.state = "outreach_done"
    happy.revision_count = 1
    happy.history = [
        _event("imported", "2026-08-15T10:00:00+00:00"),
        _event("fit_checked", "2026-08-15T10:10:00+00:00"),
        _event("draft_ready", "2026-08-15T10:30:00+00:00"),
        _event("revision_requested", "2026-08-15T10:45:00+00:00"),
        _event("draft_ready", "2026-08-15T11:00:00+00:00"),
        _event("approved_for_apply", "2026-08-15T11:15:00+00:00"),
        _event("submitted_confirmed", "2026-08-15T12:00:00+00:00"),
        _event("sheet_logged", "2026-08-15T12:10:00+00:00"),
        _event("recruiter_note_ready", "2026-08-15T12:20:00+00:00"),
        _event("outreach_done", "2026-08-15T12:30:00+00:00"),
    ]
    happy.tailoring_draft = ApplicationLoopTailoringDraftRef(
        draft_id="draft-happy",
        version=2,
        base_score=78,
        tailored_score=88,
        created_at="2026-08-15T11:00:00+00:00",
    )
    service._save_item(happy)

    portal = service.get_item(loop_ids[1])
    portal.created_at = "2026-08-15T09:00:00+00:00"
    portal.updated_at = "2026-08-15T10:00:00+00:00"
    portal.state = "ats_opened"
    portal.history = [
        _event("imported", "2026-08-15T09:00:00+00:00"),
        _event("fit_checked", "2026-08-15T09:15:00+00:00"),
        _event("draft_ready", "2026-08-15T09:30:00+00:00"),
        _event("approved_for_apply", "2026-08-15T09:45:00+00:00"),
        _event("ats_opened", "2026-08-15T09:50:00+00:00"),
    ]
    portal.ats_assist = ApplicationLoopATSAssist(
        version=1,
        task_id="portal-task",
        status="technical_issue",
        target_url=portal.job_url,
        apply_plan_path="apply_plan.json",
        preferred_resume_path="resume.pdf",
        preferred_resume_format="pdf",
        opened_at="2026-08-15T09:50:00+00:00",
        expires_at="2026-08-15T10:20:00+00:00",
        technical_issue_note="The portal rejected the resume upload.",
    )
    service._save_item(portal)

    skipped = service.get_item(loop_ids[2])
    skipped.created_at = "2026-08-14T13:00:00+00:00"
    skipped.updated_at = "2026-08-14T13:05:00+00:00"
    skipped.state = "skipped"
    skipped.history = [
        _event("imported", "2026-08-14T13:00:00+00:00"),
        _event(
            "skipped",
            "2026-08-14T13:05:00+00:00",
            "Role requires unrestricted work authorization.",
        ),
    ]
    service._save_item(skipped)

    old = service.get_item(loop_ids[3])
    old.created_at = "2026-06-01T10:00:00+00:00"
    old.updated_at = "2026-06-01T10:00:00+00:00"
    old.state = "imported"
    old.history = [_event("imported", "2026-06-01T10:00:00+00:00")]
    service._save_item(old)


def test_metrics_compute_funnel_timing_quality_and_bottleneck(tmp_path, monkeypatch) -> None:
    service, _ = _service(tmp_path, monkeypatch)

    result = service.metrics("7d")

    assert result.window_label == "Last 7 days"
    assert result.summary.total_applications == 3
    assert result.summary.fit_checked == 2
    assert result.summary.skipped == 1
    assert result.summary.draft_ready == 2
    assert result.summary.approved == 2
    assert result.summary.submitted == 1
    assert result.summary.sheet_logged == 1
    assert result.summary.outreach_done == 1
    assert result.summary.portal_issues == 1
    assert result.summary.total_revisions == 1
    assert result.summary.average_revisions_per_tailored == 0.5
    assert result.summary.average_tailoring_score_lift == 10.0
    assert result.summary.average_minutes_to_submission == 120.0
    assert result.summary.submission_rate == 33.3
    assert result.summary.sheet_logging_rate == 100.0
    assert result.summary.outreach_completion_rate == 100.0

    funnel = {stage.state: stage for stage in result.funnel}
    assert funnel["imported"].count == 3
    assert funnel["skipped"].kind == "exit"
    assert funnel["outreach_done"].percent_of_imported == 33.3

    timings = {timing.key: timing for timing in result.stage_timings}
    assert timings["intake_to_fit"].sample_count == 3
    assert timings["intake_to_fit"].average_minutes == 10.0
    assert timings["fit_to_draft"].average_minutes == 17.5
    assert timings["approval_to_submission"].average_minutes == 45.0
    assert result.bottleneck.key == "approval_to_submission"
    assert result.skip_reasons[0].reason == "Role requires unrestricted work authorization."
    assert result.portal_failure_reasons[0].reason == "The portal rejected the resume upload."
    assert result.current_state_counts == {
        "ats_opened": 1,
        "outreach_done": 1,
        "skipped": 1,
    }


def test_metrics_window_excludes_old_items_and_all_time_restores_them(tmp_path, monkeypatch) -> None:
    service, _ = _service(tmp_path, monkeypatch)

    assert service.metrics("30d").summary.total_applications == 3
    assert service.metrics("all").summary.total_applications == 4
    assert service.metrics("all").since == ""


def test_metrics_api_is_typed_and_rejects_unknown_windows(tmp_path, monkeypatch) -> None:
    service, _ = _service(tmp_path, monkeypatch)
    app.dependency_overrides[get_application_loop_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.get("/application-loop/metrics?window=7d")
        invalid = client.get("/application-loop/metrics?window=quarter")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["summary"]["total_applications"] == 3
    assert response.json()["bottleneck"]["label"] == "Approval to submission"
    assert invalid.status_code == 422
