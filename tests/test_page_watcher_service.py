from __future__ import annotations

from app.schemas.ats_autofill import AutofillField, WatcherObserveRequest
from app.services.ats_autofill_service import ATSAutofillService
from app.services.page_watcher_service import PageWatcherService


def _service() -> PageWatcherService:
    # No api_key -> deterministic heuristic path, no network.
    return PageWatcherService(autofill=ATSAutofillService(), api_key="")


def _field(field_id: str, label: str, *, input_type: str = "text", **kwargs) -> AutofillField:
    return AutofillField(
        field_id=field_id,
        selector=f"#{field_id}",
        tag=kwargs.get("tag", "input"),
        input_type=input_type,
        label=label,
        name=kwargs.get("name", field_id),
    )


def test_observe_classifies_job_description_page() -> None:
    service = _service()
    result = service.observe(
        WatcherObserveRequest(
            url="https://boards.greenhouse.io/acme/jobs/123",
            page_title="Data Scientist at Acme",
            page_text=(
                "About the role: Acme is hiring a Data Scientist. Responsibilities include Python, SQL, "
                "and machine learning. Minimum qualifications: 1 year of experience. Preferred qualifications "
                "include analytics and model deployment."
            ),
            form_fields=[],
            use_llm=False,
        )
    )

    assert result.engine == "heuristic"
    assert result.page_type == "job_description"
    assert result.jd is not None
    # The deterministic fallback only approximates the role; Claude refines it at runtime.
    assert "data" in result.jd.role.lower()


def test_observe_classifies_application_form_and_guards_sensitive_fields() -> None:
    service = _service()
    result = service.observe(
        WatcherObserveRequest(
            url="https://jobs.lever.co/acme/apply",
            page_title="Apply",
            page_text="Submit your application below.",
            form_fields=[
                _field("first_name", "First Name"),
                _field("last_name", "Last Name"),
                _field("email", "Email", input_type="email"),
                _field("phone", "Phone"),
                _field("linkedin", "LinkedIn URL", input_type="url"),
                _field("gender", "Gender"),
                _field("ssn", "Social Security Number"),
            ],
            use_llm=False,
        )
    )

    assert result.page_type in {"application_form", "both"}
    by_id = {item.field_id: item for item in result.field_suggestions}

    # Safe identity fields are suggested for fill.
    assert by_id["email"].action == "fill_text"
    assert "@" in by_id["email"].value
    assert by_id["first_name"].action == "fill_text"

    # Sensitive fields are never auto-filled.
    assert by_id["gender"].sensitive is True
    assert by_id["gender"].action == "skip_sensitive"
    assert by_id["ssn"].sensitive is True
    assert by_id["ssn"].action == "skip_sensitive"
    assert result.sensitive_count >= 2
    assert result.fillable_count >= 2


def test_observe_detects_confirmation_page() -> None:
    service = _service()
    result = service.observe(
        WatcherObserveRequest(
            url="https://jobs.lever.co/acme/apply/thanks",
            page_title="Thank you",
            page_text="Thank you for applying. Your application has been submitted.",
            form_fields=[],
            use_llm=False,
        )
    )

    assert result.page_type == "confirmation"
