from app.schemas.tracker import (
    ApplicationRowCreateRequest,
    ApplicationStatusUpdateRequest,
    SheetsLogRequest,
)
from app.config import settings
from app.services.tracker_service import TrackerService


def test_add_row():
    service = TrackerService()

    payload = ApplicationRowCreateRequest(
        company_applied="Ipsos",
        role="Data Scientist, Creative Excellence (7372)",
        salary_quoted_while_applying="$60000/year",
        job_posted_on="Jobright AI",
        applied_using="Company Website",
        status="Applied",
        link="https://example.com/job/ipsos-7372",
        job_id="ipsos_ds_7372",
        base_match_percent=78,
        tailored_match_percent=86,
        resume_version_used="base_resume_v1",
        notes="Good fit after tailoring.",
    )

    response = service.add_row(payload)

    assert response.company_applied == "Ipsos"
    assert response.role == "Data Scientist, Creative Excellence (7372)"
    assert response.status == "Applied"
    assert "saved" in response.message.lower()


def test_add_row_appends_job_id_to_role_for_tracking():
    service = TrackerService()

    payload = ApplicationRowCreateRequest(
        company_applied="Best Buy",
        role="Associate Decision Scientist, Market Share",
        salary_quoted_while_applying="N/A",
        job_posted_on="Jobright AI",
        applied_using="Company Website",
        status="Applied",
        link="https://example.com/job/best-buy-1027197br",
        job_id="1027197BR",
    )

    response = service.add_row(payload)

    assert response.role == "Associate Decision Scientist, Market Share (1027197BR)"


def test_add_row_does_not_duplicate_job_id_in_role():
    service = TrackerService()

    payload = ApplicationRowCreateRequest(
        company_applied="Seagate",
        role="Generative AI and Machine Learning Engineer - Early Career (14362)",
        salary_quoted_while_applying="N/A",
        job_posted_on="Jobright AI",
        applied_using="Company Website",
        status="Applied",
        link="https://example.com/job/seagate-14362",
        job_id="14362",
    )

    response = service.add_row(payload)

    assert response.role == "Generative AI and Machine Learning Engineer - Early Career (14362)"


def test_log_to_sheets_writes_job_id_inside_role(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "success": True,
                "script_version": "v14",
                "mode": "appended_new_row",
                "target_row": 42,
            }

    def fake_post(url, json, timeout, follow_redirects):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        captured["follow_redirects"] = follow_redirects
        return FakeResponse()

    monkeypatch.setattr(settings, "google_apps_script_url", "https://example.com/apps-script")
    monkeypatch.setattr("app.services.tracker_service.httpx.post", fake_post)

    service = TrackerService()
    response = service.log_to_sheets(
        SheetsLogRequest(
            company="Best Buy",
            role="Associate Decision Scientist, Market Share",
            salary="N/A",
            job_posted_on="Jobright AI",
            applied_using="Company Website",
            status="Applied",
            link="https://example.com/job/best-buy-1027197br",
            job_id="1027197BR",
        )
    )

    assert response.success is True
    assert captured["json"]["role"] == "Associate Decision Scientist, Market Share (1027197BR)"
    assert captured["json"]["target"] == "jobs_applied"
    assert any(
        row.company_applied == "Best Buy"
        and row.role == "Associate Decision Scientist, Market Share (1027197BR)"
        and row.job_id == "1027197BR"
        for row in service.list_rows()
    )


def test_update_status_existing_row():
    service = TrackerService()

    add_payload = ApplicationRowCreateRequest(
        company_applied="Bloomberg BNA",
        role="Data Analyst, Associate (141195)",
        salary_quoted_while_applying="$65000/year",
        job_posted_on="Jobright AI",
        applied_using="Company Website",
        status="Applied",
        link="https://example.com/job/bloomberg-141195",
    )
    service.add_row(add_payload)

    update_payload = ApplicationStatusUpdateRequest(
        company_applied="Bloomberg BNA",
        role="Data Analyst, Associate (141195)",
        status="Rejection",
        notes="Rejected after application.",
    )

    response = service.update_status(update_payload)

    assert response.company_applied == "Bloomberg BNA"
    assert response.role == "Data Analyst, Associate (141195)"
    assert response.status == "Rejection"


def test_update_status_missing_row_creates_placeholder():
    service = TrackerService()

    update_payload = ApplicationStatusUpdateRequest(
        company_applied="Tesla",
        role="Data Analyst, Field Reliability",
        status="Not Applied",
        notes="Tracking only for now.",
    )

    response = service.update_status(update_payload)

    assert response.company_applied == "Tesla"
    assert response.role == "Data Analyst, Field Reliability"
    assert response.status == "Not Applied"


def test_list_rows():
    service = TrackerService()

    payload_1 = ApplicationRowCreateRequest(
        company_applied="Caterpillar",
        role="Data Scientist (R0000361224)",
        salary_quoted_while_applying="N/A",
        job_posted_on="Jobright AI",
        applied_using="Company Website",
        status="Applied",
        link="https://example.com/job/caterpillar-r0000361224",
    )
    payload_2 = ApplicationRowCreateRequest(
        company_applied="Quantifind",
        role="Associate Data Scientist",
        salary_quoted_while_applying="N/A",
        job_posted_on="Jobright AI",
        applied_using="Company Website",
        status="Applied",
        link="https://example.com/job/quantifind-ads",
    )

    service.add_row(payload_1)
    service.add_row(payload_2)

    rows = service.list_rows()

    assert len(rows) >= 2
    assert any(row.company_applied == "Caterpillar" for row in rows)
    assert any(row.company_applied == "Quantifind" for row in rows)
