from fastapi.testclient import TestClient

from app.main import app


def test_email_classifier_detects_screening_call():
    client = TestClient(app)
    response = client.post(
        "/email/classify",
        json={
            "subject": "Schedule an initial phone screen",
            "body": "We would like to set up a 30-minute call with our recruiter.",
            "sender_email": "recruiting@exampleco.com",
            "sender_name": "ExampleCo Recruiting",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["email_type"] == "screening_interview"
    assert payload["new_status"] == "Screening Interview Call"
    assert payload["requires_review"] is False


def test_email_classifier_does_not_rewrite_acknowledgments():
    client = TestClient(app)
    response = client.post(
        "/email/classify",
        json={
            "subject": "Application confirmation - Generative AI Engineer",
            "body": "Thank you for applying. We received your application and it is under review.",
            "sender_email": "noreply@example.com",
            "sender_name": "Example Careers",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["email_type"] == "acknowledgment"
    assert payload["new_status"] == ""
    assert payload["requires_review"] is False


def test_email_classifier_treats_linkedin_sent_application_as_acknowledgment():
    client = TestClient(app)
    response = client.post(
        "/email/classify",
        json={
            "subject": "Your application to Artificial Intelligence Engineer at BeaconFire Inc.",
            "body": "",
            "sender_email": "jobs-noreply@linkedin.com",
            "sender_name": "LinkedIn",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["email_type"] == "acknowledgment"
    assert payload["new_status"] == ""
    assert payload["requires_review"] is False


def test_email_classifier_ignores_non_job_government_account_email():
    client = TestClient(app)
    response = client.post(
        "/email/classify",
        json={
            "subject": "We have taken an action on your case",
            "body": "Sign in to your account to view your case status.",
            "sender_email": "no-reply@uscis.dhs.gov",
            "sender_name": "no-reply",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["email_type"] == "ignore"
    assert payload["is_job_related"] is False
    assert payload["requires_review"] is False


def test_email_classifier_uses_dropdown_status_for_initial_rejection():
    client = TestClient(app)
    response = client.post(
        "/email/classify",
        json={
            "subject": "Verify your candidate account",
            "body": "Please confirm your email address and complete setup before we can proceed.",
            "sender_email": "workflow@myworkday.com",
            "sender_name": "Workday",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["email_type"] == "initial_rejection_followup"
    assert payload["new_status"] == "Initial Rejection - Subject to further details"
    assert payload["requires_review"] is True


def test_email_classifier_detects_decision_not_to_move_rejection():
    client = TestClient(app)
    response = client.post(
        "/email/classify",
        json={
            "subject": "Thanks for your interest in Traackr, Akhilesh",
            "body": "After reviewing your work and experience, we've made the decision to not move forward.",
            "sender_email": "recruiting@traackr.com",
            "sender_name": "Traackr",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["company_name"] == "Traackr"
    assert payload["email_type"] == "rejection"
    assert payload["new_status"] == "Rejection"
    assert payload["requires_review"] is False


def test_email_classifier_rejection_overrides_polite_acknowledgment_language():
    client = TestClient(app)
    response = client.post(
        "/email/classify",
        json={
            "subject": "Thanks for your interest in Traackr, Akhilesh",
            "body": (
                "Hi Akhilesh, Thank you for your application to Traackr. "
                "After reviewing your work and experience, we've made the decision to not move for"
            ),
            "sender_email": "recruiting@traackr.com",
            "sender_name": "Traackr",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["email_type"] == "rejection"
    assert payload["new_status"] == "Rejection"
    assert payload["matched_rule"] == "rejection"


def test_llm_status_endpoint_defaults_to_mock():
    client = TestClient(app)
    response = client.get("/llm/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] in {"mock", "ollama"}
    assert "available" in payload
