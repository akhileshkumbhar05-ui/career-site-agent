import pytest
from uuid import uuid4
from fastapi import HTTPException

from app.config import settings
from app.dependencies import get_job_quality_gate_service, get_llm_match_service, get_tracker_service
from app.schemas.copilot import (
    SHEET_COLUMNS,
    ConfirmApplicationLogRequest,
    ManualJDAnalyzeRequest,
    PrepareApplicationLogRequest,
)
from app.services.copilot_service import ManualJDCopilotService


def _service():
    return ManualJDCopilotService(
        matcher=get_llm_match_service(),
        quality_gate=get_job_quality_gate_service(),
        tracker=get_tracker_service(),
        data_dir=f"data/manual_copilot_tests/{uuid4().hex}",
    )


def test_analyze_manual_jd_returns_legacy_sheet_preview():
    service = _service()

    result = service.analyze(
        ManualJDAnalyzeRequest(
            company="Signal Analytics",
            role="Junior Data Analyst",
            location="United States",
            source="Jobright AI",
            link="https://boards.greenhouse.io/signal/jobs/123",
            jd_text=(
                "Junior Data Analyst role in the United States. Responsibilities include SQL, Python, "
                "dashboarding, data quality checks, and stakeholder reporting. No clearance required."
            ),
        )
    )

    assert tuple(result.sheet_preview.keys()) == SHEET_COLUMNS
    assert result.sheet_preview["Job Posted On"] == "Jobright AI"
    assert result.sheet_preview["Applied Using"] == "Company Website"
    assert result.sheet_preview["Date"] == ""
    assert result.sheet_preview["Status"] == ""
    assert result.apply_plan.submission_boundary.startswith("The system may prepare data")


def test_prepare_log_returns_exact_blank_status_proposal_before_submission():
    service = _service()

    result = service.prepare_log(
        PrepareApplicationLogRequest(
            lead_id="jobright_signal_123",
            company="Signal Analytics",
            role="Junior Data Analyst",
            link="https://boards.greenhouse.io/signal/jobs/123?utm_source=jobright",
            salary_quoted="N/A",
            source="Jobright AI",
        )
    )

    assert result.action == "ready"
    assert tuple(result.row.keys()) == SHEET_COLUMNS
    assert result.row["Date"] == ""
    assert result.row["Status"] == ""
    assert result.row["Job Posted On"] == "Jobright AI"
    assert result.row["Applied Using"] == "Company Website"
    assert result.requires_human_confirmation is True


def test_prepare_technical_issue_uses_controlled_status_without_submission_confirmation():
    service = _service()

    result = service.prepare_log(
        PrepareApplicationLogRequest(
            company="Portal Labs",
            role="ML Engineer",
            link="https://portal.example/jobs/1",
            source="Company Website",
            technical_issue=True,
        )
    )

    assert result.action == "ready"
    assert result.row["Date"]
    assert result.row["Status"] == "Not Yet Applied Due to Technical Issue"
    assert result.requires_human_confirmation is False


def test_applied_status_requires_human_confirmation():
    service = _service()

    with pytest.raises(HTTPException) as exc:
        service.confirm_log(
            ConfirmApplicationLogRequest(
                company="Signal Analytics",
                role="Junior Data Analyst",
                link="https://example.com/job",
                status="Applied",
                human_confirmed_submission=False,
            )
        )

    assert exc.value.status_code == 400
    assert "manual submission confirmation" in exc.value.detail


def test_technical_issue_uses_controlled_status_without_applied_confirmation():
    service = _service()

    result = service.confirm_log(
        ConfirmApplicationLogRequest(
            company="Portal Labs",
            role="ML Engineer",
            link="https://portal.example/jobs/1",
            source="Company Website",
            technical_issue=True,
        )
    )

    assert result.success is True
    assert result.action == "created"
    assert result.row["Status"] == "Not Yet Applied Due to Technical Issue"
    assert result.destination == "local_tracker"


def test_duplicate_prevention_checks_link_first():
    service = _service()
    payload = ConfirmApplicationLogRequest(
        company="Duplicate Co",
        role="Data Scientist",
        link="https://duplicate.example/jobs/1",
        source="LinkedIn",
        human_confirmed_submission=True,
    )

    first = service.confirm_log(payload)
    second = service.confirm_log(
        ConfirmApplicationLogRequest(
            company="Renamed Duplicate Co",
            role="Different Title",
            link="https://duplicate.example/jobs/1",
            source="LinkedIn",
            human_confirmed_submission=True,
        )
    )

    assert first.action == "created"
    assert second.action == "duplicate_skipped"
    assert second.row["Applied Using"] == "Company Website"


def test_duplicate_prevention_canonicalizes_tracking_parameters():
    service = _service()
    first = service.confirm_log(
        ConfirmApplicationLogRequest(
            company="Canonical Co",
            role="Data Analyst",
            link="https://jobs.example.com/roles/42?utm_source=jobright&ref=feed",
            source="Jobright AI",
            human_confirmed_submission=True,
        )
    )
    proposal = service.prepare_log(
        PrepareApplicationLogRequest(
            company="Canonical Company",
            role="Analytics Specialist",
            link="https://jobs.example.com/roles/42/",
            source="LinkedIn",
        )
    )

    assert first.action == "created"
    assert proposal.action == "duplicate"
    assert proposal.duplicate_reason == "link"


def test_confirm_log_commits_to_configured_google_sheet_after_confirmation(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "success": True,
                "script_version": "v16",
                "mode": "appended_new_row",
                "target_row": 42,
            }

    def fake_post(url, json, timeout, follow_redirects):
        captured.update(json)
        return FakeResponse()

    monkeypatch.setattr(settings, "google_apps_script_url", "https://example.com/apps-script")
    monkeypatch.setattr("app.services.tracker_service.httpx.post", fake_post)

    result = _service().confirm_log(
        ConfirmApplicationLogRequest(
            company="Confirmed Sheets Co",
            role="Business Data Analyst",
            link="https://careers.example.com/jobs/confirmed-42",
            source="Jobright AI",
            human_confirmed_submission=True,
        )
    )

    assert result.success is True
    assert result.action == "created"
    assert result.destination == "google_sheets"
    assert captured["human_confirmed_submission"] is True
    assert captured["status"] == "Applied"
