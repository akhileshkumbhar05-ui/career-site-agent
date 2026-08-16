from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_third_eye_closeout_service
from app.main import app
from app.schemas.application_loop import (
    ApplicationLoopATSAssist,
    ApplicationLoopBatchImportRequest,
)
from app.schemas.application_sprint import ApplicationSprintCreateRequest
from app.schemas.ats_autofill import AutofillAutopilotContextResponse
from app.schemas.sheets import SHEET_COLUMNS
from app.schemas.third_eye_closeout import ThirdEyeCloseoutRequest, ThirdEyeCloseoutReviewRequest
from app.schemas.tracker import SheetsLogResponse
from app.services.application_loop_service import ApplicationLoopService, InvalidApplicationLoopTransition
from app.services.application_sprint_service import ApplicationSprintService
from app.services.third_eye_closeout_service import ThirdEyeCloseoutService


NOW = "2026-08-16T20:00:00+00:00"


class FakeTracker:
    def __init__(self, result: SheetsLogResponse | None = None) -> None:
        self.sheets_configured = True
        self.result = result or SheetsLogResponse(
            success=True,
            message="Logged to Google Sheets.",
            mode="created",
            target_row=42,
        )
        self.calls = []

    def log_to_sheets(self, payload):
        self.calls.append(payload)
        return self.result


class FakeAutopilot:
    def __init__(self, loop_id: str) -> None:
        self.loop_id = loop_id

    def get_task(self, task_id=""):
        if task_id and task_id != "task-1":
            return {}
        return {"task_id": "task-1", "loop_id": self.loop_id}

    def context(self, payload):
        return AutofillAutopilotContextResponse(
            enabled=bool(self.loop_id),
            task_id="task-1" if self.loop_id else "",
            loop_id=self.loop_id,
        )


def _services(tmp_path, monkeypatch, tracker_result: SheetsLogResponse | None = None):
    monkeypatch.setenv("CAREER_SITE_AGENT_DB_PATH", str(tmp_path / "third_eye_closeout.db"))
    clock = lambda: datetime(2026, 8, 16, 20, 0, tzinfo=UTC)
    loop_service = ApplicationLoopService(clock=clock)
    imported = loop_service.import_batch(
        ApplicationLoopBatchImportRequest.model_validate(
            {
                "items": [
                    {
                        "company": "Portal Labs",
                        "role": "Operations Data Analyst",
                        "job_url": "https://careers.portallabs.example/jobs/42?utm_source=jobright",
                        "jd_text": "Analyze operational data using Python, SQL, and dashboards. " * 4,
                        "source": "Jobright AI",
                    },
                    {
                        "company": "Next Company",
                        "role": "Business Data Analyst",
                        "job_url": "https://jobs.next.example/analyst-2",
                        "jd_text": "Build operational reports and stakeholder-ready analysis. " * 4,
                        "source": "LinkedIn",
                    },
                ]
            }
        )
    )
    first, second = [outcome.loop_item for outcome in imported.outcomes]
    first.state = "ats_opened"
    first.ats_assist = ApplicationLoopATSAssist(
        version=1,
        task_id="task-1",
        status="safe_fields_filled",
        target_url=first.canonical_job_url,
        apply_plan_path="data/test-plan.json",
        preferred_resume_path="data/test-resume.pdf",
        preferred_resume_format="pdf",
        opened_at=NOW,
        expires_at="2026-08-16T21:00:00+00:00",
    )
    loop_service._save_item(first)
    sprint_service = ApplicationSprintService(loop_service=loop_service, clock=clock)
    sprint_service.create(
        ApplicationSprintCreateRequest(
            name="Monday sprint",
            target_count=2,
            loop_ids=[first.loop_id, second.loop_id],
        )
    )
    tracker = FakeTracker(tracker_result)
    closeout = ThirdEyeCloseoutService(
        loop_service=loop_service,
        sprint_service=sprint_service,
        tracker=tracker,
        autofill_autopilot=FakeAutopilot(first.loop_id),
    )
    return loop_service, sprint_service, tracker, closeout, first.loop_id, second.loop_id


def test_confirmed_submission_logs_exact_sheet_row_and_advances_sprint(tmp_path, monkeypatch) -> None:
    loop_service, _, tracker, service, first_id, second_id = _services(tmp_path, monkeypatch)

    review = service.review(ThirdEyeCloseoutReviewRequest(loop_id=first_id))
    assert review.matched is True
    assert review.match_source == "explicit_loop"
    assert tuple(review.submitted_sheet_row) == SHEET_COLUMNS
    assert review.submitted_sheet_row["Job Posted On"] == "Jobright AI"
    assert review.submitted_sheet_row["Applied Using"] == "Company Website"
    assert review.submitted_sheet_row["Status"] == "Applied"
    assert review.claude_calls == 0

    with pytest.raises(InvalidApplicationLoopTransition, match="Manual submission confirmation"):
        service.commit(
            ThirdEyeCloseoutRequest(
                loop_id=first_id,
                outcome="submitted_confirmed",
                note="I submitted the application.",
            )
        )
    assert tracker.calls == []

    result = service.commit(
        ThirdEyeCloseoutRequest(
            loop_id=first_id,
            outcome="submitted_confirmed",
            note="I reviewed the ATS confirmation page after submitting manually.",
            human_confirmed_submission=True,
            salary_quoted="$85,000",
            source="Jobright AI",
            applied_using="Company Website",
        )
    )

    assert result.loop_item.state == "sheet_logged"
    assert result.sheet_logged is True
    assert tuple(result.sheet_row) == SHEET_COLUMNS
    assert result.sheet_row["Salary Quoted while Applying"] == "$85,000"
    assert tracker.calls[0].human_confirmed_submission is True
    assert tracker.calls[0].status == "Applied"
    assert result.progress.current_loop_id == second_id
    assert result.progress.next_company == "Next Company"
    assert result.progress.next_action == "Run Fit Gate"
    assert result.claude_calls == 0
    assert loop_service.get_item(first_id).state == "sheet_logged"

    repeated = service.commit(
        ThirdEyeCloseoutRequest(
            loop_id=first_id,
            outcome="submitted_confirmed",
            note="I reviewed the existing confirmation again.",
            human_confirmed_submission=True,
        )
    )
    assert repeated.already_recorded is True
    assert repeated.sheet_result.mode == "already_logged"
    assert len(tracker.calls) == 1


def test_failed_sheet_write_keeps_confirmed_submission_retryable(tmp_path, monkeypatch) -> None:
    failed = SheetsLogResponse(success=False, message="Google Apps Script timed out.")
    loop_service, _, tracker, service, first_id, second_id = _services(tmp_path, monkeypatch, failed)

    first = service.commit(
        ThirdEyeCloseoutRequest(
            loop_id=first_id,
            outcome="submitted_confirmed",
            note="I reviewed the ATS confirmation page.",
            human_confirmed_submission=True,
        )
    )
    assert first.loop_item.state == "submitted_confirmed"
    assert first.sheet_logged is False
    assert first.progress.current_loop_id == first_id
    assert first.progress.next_action == "Log to Sheets"
    assert "Sheets logging failed" in first.message

    tracker.result = SheetsLogResponse(success=True, message="Duplicate found.", mode="duplicate_skipped")
    retried = service.commit(
        ThirdEyeCloseoutRequest(
            loop_id=first_id,
            outcome="submitted_confirmed",
            note="Retrying the confirmed canonical row.",
            human_confirmed_submission=True,
        )
    )
    assert retried.already_recorded is True
    assert retried.loop_item.state == "sheet_logged"
    assert retried.progress.current_loop_id == second_id
    assert len(tracker.calls) == 2
    assert loop_service.get_item(first_id).state == "sheet_logged"


def test_portal_issue_logs_controlled_status_without_marking_applied(tmp_path, monkeypatch) -> None:
    loop_service, _, tracker, service, first_id, _ = _services(tmp_path, monkeypatch)

    result = service.commit(
        ThirdEyeCloseoutRequest(
            loop_id=first_id,
            outcome="technical_issue",
            note="The ATS rejected the resume upload before submission.",
            applied_using="Company Website",
        )
    )

    assert result.outcome == "technical_issue"
    assert result.loop_item.state == "ats_opened"
    assert result.loop_item.ats_assist.status == "technical_issue"
    assert result.sheet_logged is False
    assert result.sheet_row["Status"] == "Not Yet Applied Due to Technical Issue"
    assert tracker.calls[0].technical_issue is True
    assert tracker.calls[0].human_confirmed_submission is False
    assert result.progress.current_loop_id == first_id
    assert result.progress.next_action == "Resolve portal issue"
    assert "not marked Applied" in result.message
    assert loop_service.get_item(first_id).state == "ats_opened"


def test_closeout_review_resolves_autofill_task_and_api_enforces_confirmation(tmp_path, monkeypatch) -> None:
    _, _, _, service, first_id, _ = _services(tmp_path, monkeypatch)
    by_task = service.review(ThirdEyeCloseoutReviewRequest(task_id="task-1"))
    assert by_task.matched is True
    assert by_task.match_source == "autofill_task"
    assert by_task.loop_item.loop_id == first_id

    app.dependency_overrides[get_third_eye_closeout_service] = lambda: service
    try:
        client = TestClient(app)
        review = client.post(
            "/application-loop/third-eye-closeout/review",
            json={"loop_id": first_id, "url": "https://careers.portallabs.example/confirmation"},
        )
        rejected = client.post(
            "/application-loop/third-eye-closeout",
            json={
                "loop_id": first_id,
                "outcome": "submitted_confirmed",
                "note": "Application submitted manually.",
                "human_confirmed_submission": False,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert review.status_code == 200
    assert review.json()["matched"] is True
    assert review.json()["claude_calls"] == 0
    assert rejected.status_code == 409
    assert "Manual submission confirmation" in rejected.json()["detail"]
