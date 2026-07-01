import pytest
from uuid import uuid4
from fastapi import HTTPException

from app.dependencies import get_job_quality_gate_service, get_llm_match_service, get_tracker_service
from app.schemas.copilot import SHEET_COLUMNS, ConfirmApplicationLogRequest, ManualJDAnalyzeRequest
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
    assert result.apply_plan.submission_boundary.startswith("The system may prepare data")


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
    assert second.row["Applied Using"] == "LinkedIn"
