from app.schemas.tracker import (
    ApplicationRowCreateRequest,
    ApplicationStatusUpdateRequest,
)
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