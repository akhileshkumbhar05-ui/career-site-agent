from fastapi.testclient import TestClient

from app.dependencies import get_third_eye_intake_service
from app.main import app
from app.schemas.application_loop import (
    ApplicationLoopBatchImportRequest,
    ApplicationLoopBatchItemRequest,
    ThirdEyeIntakeRequest,
)
from app.schemas.application_sprint import ApplicationSprintCreateRequest
from app.services.application_loop_service import ApplicationLoopService
from app.services.application_sprint_service import ApplicationSprintService
from app.services.third_eye_intake_service import ThirdEyeIntakeService


def _services(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_SITE_AGENT_DB_PATH", str(tmp_path / "third_eye_intake.db"))
    loop_service = ApplicationLoopService()
    sprint_service = ApplicationSprintService(loop_service=loop_service)
    intake_service = ThirdEyeIntakeService(
        loop_service=loop_service,
        sprint_service=sprint_service,
    )
    return loop_service, sprint_service, intake_service


def _job(index: int) -> ApplicationLoopBatchItemRequest:
    return ApplicationLoopBatchItemRequest(
        company=f"Company {index}",
        role=f"Data Analyst {index}",
        job_url=f"https://careers.example.com/jobs/data-analyst-{index}?utm_source=jobright",
        jd_text="Analyze operational data using Python, SQL, and stakeholder-ready reporting. " * 3,
        source="Jobright AI",
    )


def _import(loop_service: ApplicationLoopService, *items: ApplicationLoopBatchItemRequest):
    return loop_service.import_batch(ApplicationLoopBatchImportRequest(items=list(items)))


def test_review_and_commit_adds_a_new_job_to_the_open_sprint_without_claude(tmp_path, monkeypatch) -> None:
    loop_service, sprint_service, intake_service = _services(tmp_path, monkeypatch)
    seed = _import(loop_service, _job(1)).outcomes[0].loop_item
    sprint = sprint_service.create(
        ApplicationSprintCreateRequest(name="Morning sprint", target_count=2, loop_ids=[seed.loop_id])
    )

    review = intake_service.review(_job(2))
    assert review.valid is True
    assert review.existing_loop_item is None
    assert review.canonical_job_url == "https://careers.example.com/jobs/data-analyst-2"
    assert review.sprint.sprint_id == sprint.sprint_id
    assert review.sprint.open_slots == 1
    assert review.recommended_destination == "active_sprint"
    assert review.claude_calls == 0

    committed = intake_service.commit(
        ThirdEyeIntakeRequest(**_job(2).model_dump(), destination="active_sprint")
    )
    assert committed.action == "added_to_sprint"
    assert committed.import_status == "imported"
    assert committed.sprint.open_slots == 0
    assert committed.loop_item.source == "Jobright AI"
    assert committed.claude_calls == 0

    repeated = intake_service.commit(
        ThirdEyeIntakeRequest(**_job(2).model_dump(), destination="active_sprint")
    )
    assert repeated.action == "duplicate_in_sprint"
    assert repeated.import_status == "duplicate"
    assert repeated.loop_item.loop_id == committed.loop_item.loop_id
    assert len(sprint_service.get(sprint.sprint_id).items) == 2


def test_active_sprint_destination_falls_back_to_inbox_when_no_slot_exists(tmp_path, monkeypatch) -> None:
    loop_service, sprint_service, intake_service = _services(tmp_path, monkeypatch)
    seed = _import(loop_service, _job(1)).outcomes[0].loop_item
    sprint_service.create(
        ApplicationSprintCreateRequest(name="Full sprint", target_count=1, loop_ids=[seed.loop_id])
    )

    committed = intake_service.commit(
        ThirdEyeIntakeRequest(**_job(2).model_dump(), destination="active_sprint")
    )
    assert committed.action == "added_to_inbox"
    assert committed.sprint.open_slots == 0
    assert "no open slots" in committed.message
    assert len(loop_service.list_items()) == 2

    repeated = intake_service.commit(
        ThirdEyeIntakeRequest(**_job(2).model_dump(), destination="active_sprint")
    )
    assert repeated.action == "duplicate_inbox"
    assert repeated.import_status == "duplicate"


def test_third_eye_intake_api_reviews_validates_and_commits(tmp_path, monkeypatch) -> None:
    _, _, intake_service = _services(tmp_path, monkeypatch)
    app.dependency_overrides[get_third_eye_intake_service] = lambda: intake_service
    try:
        client = TestClient(app)
        review = client.post(
            "/application-loop/third-eye-intake/review",
            json=_job(3).model_dump(),
        )
        committed = client.post(
            "/application-loop/third-eye-intake",
            json={**_job(3).model_dump(), "destination": "inbox"},
        )
        invalid = client.post(
            "/application-loop/third-eye-intake",
            json={"destination": "inbox"},
        )
    finally:
        app.dependency_overrides.clear()

    assert review.status_code == 200
    assert review.json()["recommended_destination"] == "inbox"
    assert review.json()["claude_calls"] == 0
    assert committed.status_code == 200
    assert committed.json()["action"] == "added_to_inbox"
    assert committed.json()["claude_calls"] == 0
    assert invalid.status_code == 422
    assert "job URL" in invalid.json()["detail"]
