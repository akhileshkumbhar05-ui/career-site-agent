from fastapi.testclient import TestClient

from app.dependencies import get_application_loop_service
from app.main import app
from app.schemas.application_loop import ApplicationLoopBatchImportRequest
from app.services.application_loop_service import ApplicationLoopService


def _service(tmp_path, monkeypatch) -> ApplicationLoopService:
    monkeypatch.setenv("CAREER_SITE_AGENT_DB_PATH", str(tmp_path / "application_loop.db"))
    return ApplicationLoopService()


def test_batch_import_is_partial_persistent_and_deduplicated_in_priority_order(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)
    response = service.import_batch(
        ApplicationLoopBatchImportRequest.model_validate(
            {
                "items": [
                    {
                        "company": "Credit One Bank",
                        "role": "Operations Data Analyst I",
                        "job_url": "https://careers.creditonebank.com/jobs/17893342-operations-data-analyst?utm_source=jobright",
                        "jd_text": "Role: Operations Data Analyst I\nCompany: Credit One Bank\nAnalyze operations data.",
                    },
                    {
                        "company": "Different display name",
                        "role": "Different display role",
                        "job_url": "https://careers.creditonebank.com/jobs/17893342-operations-data-analyst?utm_campaign=daily",
                    },
                    {
                        "company": " credit one bank ",
                        "role": "operations data analyst i",
                        "job_url": "https://example.com/a-different-posting",
                    },
                    {},
                ]
            }
        )
    )

    assert response.summary.model_dump() == {
        "requested": 4,
        "imported": 1,
        "duplicate": 2,
        "invalid": 1,
    }
    assert [outcome.status for outcome in response.outcomes] == [
        "imported",
        "duplicate",
        "duplicate",
        "invalid",
    ]
    assert response.outcomes[1].reason.startswith("Canonical job link")
    assert response.outcomes[2].reason.startswith("Company and role")
    assert response.outcomes[3].loop_item is None

    items = service.list_items()
    assert len(items) == 1
    assert items[0].batch_id == response.batch_id
    assert items[0].jd_text.endswith("Analyze operations data.")
    assert "utm_" not in items[0].canonical_job_url


def test_batch_import_infers_identity_from_raw_jd_and_url(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)
    response = service.import_batch(
        ApplicationLoopBatchImportRequest.model_validate(
            {
                "items": [
                    {
                        "jd_text": "Job Title: Data Quality Analyst\nCompany: Northwind Analytics\nDescription: Build trusted reports.",
                        "source": "LinkedIn",
                    },
                    {
                        "job_url": "https://careers.creditonebank.com/jobs/17893342-operations-data-analyst",
                    },
                ]
            }
        )
    )

    assert response.summary.imported == 2
    raw_jd_item = response.outcomes[0].loop_item
    url_item = response.outcomes[1].loop_item
    assert raw_jd_item is not None
    assert raw_jd_item.company == "Northwind Analytics"
    assert raw_jd_item.role == "Data Quality Analyst"
    assert raw_jd_item.source == "LinkedIn"
    assert url_item is not None
    assert url_item.company == "Creditonebank"
    assert url_item.role == "Operations Data Analyst"


def test_application_loop_batch_api_imports_and_lists_items(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)
    app.dependency_overrides[get_application_loop_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post(
            "/application-loop/batches",
            json={
                "items": [
                    {
                        "company": "Contoso",
                        "role": "Business Data Analyst",
                        "job_url": "https://jobs.contoso.com/business-data-analyst",
                        "source": "Jobright AI",
                    }
                ]
            },
        )
        listed = client.get("/application-loop/items?limit=10")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["summary"]["imported"] == 1
    assert listed.status_code == 200
    assert listed.json()[0]["company"] == "Contoso"


def test_application_loop_batch_api_caps_a_batch_at_ten_items(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)
    app.dependency_overrides[get_application_loop_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/application-loop/batches",
            json={"items": [{"job_url": f"https://example.com/role-{index}"} for index in range(11)]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
