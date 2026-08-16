from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_application_loop_service, get_autofill_autopilot_service
from app.main import app
from app.schemas.application_loop import (
    ApplicationLoopATSArmRequest,
    ApplicationLoopATSOutcomeRequest,
    ApplicationLoopBatchImportRequest,
    ApplicationLoopExportHandoff,
    ApplicationLoopTransitionRequest,
)
from app.schemas.ats_autofill import AutofillAutopilotArmResponse
from app.services.application_loop_service import ApplicationLoopService, InvalidApplicationLoopTransition
from app.services.autofill_autopilot_service import AutofillAutopilotService


class FakeAutofillAutopilot:
    def __init__(self) -> None:
        self.arm_requests = []
        self.task = {}

    def arm(self, payload):
        self.arm_requests.append(payload)
        self.task = {
            "task_id": "autofill_test_task",
            "loop_id": payload.loop_id,
            "target_url": payload.url,
            "status": "armed",
            "last_result": {},
        }
        return AutofillAutopilotArmResponse(
            armed=True,
            task_id="autofill_test_task",
            loop_id=payload.loop_id,
            target_url=payload.url,
            apply_plan_path=payload.apply_plan_path,
            expires_at="2026-08-16T20:30:00+00:00",
            message="Armed.",
        )

    def get_task(self, task_id=""):
        if task_id and task_id != self.task.get("task_id"):
            return {}
        return self.task


def _ready_service(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_SITE_AGENT_DB_PATH", str(tmp_path / "ats_assist.db"))
    autopilot = FakeAutofillAutopilot()
    service = ApplicationLoopService(autofill_autopilot=autopilot)
    imported = service.import_batch(
        ApplicationLoopBatchImportRequest.model_validate(
            {
                "items": [
                    {
                        "company": "Portal Labs",
                        "role": "Data Analyst",
                        "job_url": "https://careers.portallabs.example/jobs/42?utm_source=jobright",
                        "jd_text": "Analyze operational data with Python and SQL. " * 8,
                        "source": "Jobright AI",
                    }
                ]
            }
        )
    )
    item = imported.outcomes[0].loop_item
    for state in ("fit_checked", "draft_ready", "approved_for_apply"):
        item = service.transition(item, ApplicationLoopTransitionRequest(target_state=state, actor="agent"))

    export_dir = tmp_path / "export"
    export_dir.mkdir()
    docx_path = export_dir / "resume.docx"
    pdf_path = export_dir / "resume.pdf"
    plan_path = export_dir / "apply_plan.json"
    docx_path.write_bytes(b"docx")
    pdf_path.write_bytes(b"pdf")
    plan_path.write_text('{"job":{"official_url":"https://careers.portallabs.example/jobs/42"}}', encoding="utf-8")
    item.export_handoff = ApplicationLoopExportHandoff(
        version=1,
        draft_id="draft-1",
        exported_at="2026-08-16T20:00:00+00:00",
        quality_passed=True,
        docx_ready=True,
        pdf_ready=True,
        docx_download_path="/docx",
        pdf_download_path="/pdf",
        prepared_resume_docx_path=str(docx_path),
        prepared_resume_pdf_path=str(pdf_path),
        prepared_apply_plan_path=str(plan_path),
    )
    service._save_item(item)
    return service, autopilot, item.loop_id


def test_ats_assist_arms_only_the_approved_export_and_persists_review_results(tmp_path, monkeypatch) -> None:
    service, autopilot, loop_id = _ready_service(tmp_path, monkeypatch)

    armed = service.arm_ats_assist(loop_id, ApplicationLoopATSArmRequest())

    assert armed.loop_item.state == "ats_opened"
    assert armed.assist.preferred_resume_format == "pdf"
    assert Path(armed.assist.preferred_resume_path).name == "resume.pdf"
    assert autopilot.arm_requests[0].overwrite is False
    assert autopilot.arm_requests[0].open_browser is False
    assert autopilot.arm_requests[0].loop_id == loop_id

    autopilot.task.update(
        {
            "last_result_at": "2026-08-16T20:05:00+00:00",
            "last_result": {
                "filled_count": 3,
                "total_fields": 7,
                "fillable_count": 3,
                "manual_count": 2,
                "skipped_count": 2,
                "results": [
                    {"field_id": "name", "label": "Full name", "action": "fill_text"},
                    {
                        "field_id": "resume",
                        "label": "Resume upload",
                        "action": "manual_upload",
                        "reason": "Browser security requires a manual upload.",
                    },
                    {
                        "field_id": "race",
                        "label": "Race or ethnicity",
                        "action": "skip_sensitive",
                        "reason": "Protected demographic question.",
                        "sensitive": True,
                    },
                    {
                        "field_id": "custom",
                        "label": "Describe your domain experience",
                        "action": "skip_unknown",
                        "reason": "No grounded answer is available.",
                    },
                ],
            },
        }
    )

    synced = service.sync_ats_assist(loop_id)

    assert synced.assist.status == "review_required"
    assert synced.assist.filled_count == 3
    assert [item.label for item in synced.assist.review_items] == [
        "Resume upload",
        "Race or ethnicity",
        "Describe your domain experience",
    ]
    assert synced.assist.review_items[1].sensitive is True


def test_failed_export_checks_require_and_persist_a_human_review_note(tmp_path, monkeypatch) -> None:
    service, _, loop_id = _ready_service(tmp_path, monkeypatch)
    item = service.get_item(loop_id)
    item.export_handoff.quality_passed = False
    service._save_item(item)

    with pytest.raises(InvalidApplicationLoopTransition, match="review note"):
        service.arm_ats_assist(loop_id, ApplicationLoopATSArmRequest())

    armed = service.arm_ats_assist(
        loop_id,
        ApplicationLoopATSArmRequest(
            quality_review_note="The only failed check is the optional PDF page-count warning; the DOCX was reviewed."
        ),
    )
    assert armed.assist.quality_review_note.startswith("The only failed check")
    assert "Quality review:" in armed.loop_item.history[-1].note


def test_ats_outcomes_create_sheet_proposals_without_automatic_submission(tmp_path, monkeypatch) -> None:
    service, autopilot, loop_id = _ready_service(tmp_path, monkeypatch)
    service.arm_ats_assist(loop_id, ApplicationLoopATSArmRequest())

    issue = service.record_ats_outcome(
        loop_id,
        ApplicationLoopATSOutcomeRequest(
            outcome="technical_issue",
            note="The portal rejected the resume upload before submission.",
        ),
    )

    assert issue.loop_item.state == "ats_opened"
    assert issue.assist.status == "technical_issue"
    assert issue.sheet_row_proposal["Status"] == "Not Yet Applied Due to Technical Issue"
    assert issue.sheet_row_proposal["Job Posted On"] == "Jobright AI"
    assert issue.sheet_row_proposal["Applied Using"] == "Company Website"
    assert tuple(issue.sheet_row_proposal) == (
        "Date",
        "Company Applied",
        "Role",
        "Salary Quoted while Applying",
        "Job Posted On",
        "Applied Using",
        "Status",
        "Link",
    )

    autopilot.task.update(
        {
            "last_result_at": "2026-08-16T20:10:00+00:00",
            "last_result": {
                "filled_count": 1,
                "total_fields": 2,
                "results": [{"field_id": "resume", "label": "Resume", "action": "manual_upload"}],
            },
        }
    )
    assert service.sync_ats_assist(loop_id).assist.status == "technical_issue"

    with pytest.raises(InvalidApplicationLoopTransition, match="Manual submission confirmation"):
        service.record_ats_outcome(
            loop_id,
            ApplicationLoopATSOutcomeRequest(
                outcome="submitted_confirmed",
                note="Application submitted in the company portal.",
            ),
        )

    submitted = service.record_ats_outcome(
        loop_id,
        ApplicationLoopATSOutcomeRequest(
            outcome="submitted_confirmed",
            note="I reviewed the confirmation page after submitting manually.",
            human_confirmed_submission=True,
        ),
    )
    assert submitted.loop_item.state == "submitted_confirmed"
    assert submitted.sheet_row_proposal["Status"] == "Applied"
    assert submitted.loop_item.history[-1].human_confirmed_submission is True
    assert service.sync_ats_assist(loop_id).assist.status == "submitted_confirmed"


def test_ats_assist_api_arms_syncs_and_requires_submission_confirmation(tmp_path, monkeypatch) -> None:
    service, _, loop_id = _ready_service(tmp_path, monkeypatch)
    app.dependency_overrides[get_application_loop_service] = lambda: service
    try:
        client = TestClient(app)
        armed = client.post(f"/application-loop/items/{loop_id}/ats-assist/arm", json={})
        synced = client.get(f"/application-loop/items/{loop_id}/ats-assist")
        rejected = client.post(
            f"/application-loop/items/{loop_id}/ats-assist/outcome",
            json={
                "outcome": "submitted_confirmed",
                "note": "Application submitted in the company ATS.",
                "human_confirmed_submission": False,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert armed.status_code == 200
    assert armed.json()["loop_item"]["state"] == "ats_opened"
    assert synced.status_code == 200
    assert synced.json()["assist"]["status"] == "armed"
    assert rejected.status_code == 409


def test_extension_result_endpoint_syncs_the_application_inbox_automatically(tmp_path, monkeypatch) -> None:
    service, _, loop_id = _ready_service(tmp_path, monkeypatch)
    autopilot = AutofillAutopilotService(state_path=str(tmp_path / "autopilot.json"))
    service.autofill_autopilot = autopilot
    armed = service.arm_ats_assist(loop_id, ApplicationLoopATSArmRequest())
    app.dependency_overrides[get_application_loop_service] = lambda: service
    app.dependency_overrides[get_autofill_autopilot_service] = lambda: autopilot
    try:
        response = TestClient(app).post(
            "/autofill/autopilot/result",
            json={
                "task_id": armed.assist.task_id,
                "url": armed.assist.target_url,
                "filled_count": 2,
                "total_fields": 4,
                "fillable_count": 2,
                "manual_count": 1,
                "skipped_count": 1,
                "results": [
                    {"field_id": "email", "label": "Email", "action": "fill_text"},
                    {
                        "field_id": "salary",
                        "label": "Expected salary",
                        "action": "manual_review",
                        "reason": "Candidate decision required.",
                    },
                ],
            },
        )
    finally:
        app.dependency_overrides.clear()

    saved = service.get_item(loop_id)
    assert response.status_code == 200
    assert response.json()["loop_id"] == loop_id
    assert saved.ats_assist.status == "review_required"
    assert saved.ats_assist.filled_count == 2
    assert saved.ats_assist.review_items[0].label == "Expected salary"
