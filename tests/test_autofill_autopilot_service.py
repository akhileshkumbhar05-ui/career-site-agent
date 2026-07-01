from app.schemas.ats_autofill import (
    AutofillAutopilotArmRequest,
    AutofillAutopilotContextRequest,
    AutofillAutopilotResultRequest,
)
from app.services.autofill_autopilot_service import AutofillAutopilotService


def sample_apply_plan() -> dict:
    return {
        "job": {
            "company": "Example Robotics",
            "role": "Junior Data Scientist",
            "official_url": "https://jobs.example.com/apply/junior-data-scientist-123",
            "job_id": "123",
        },
        "ats_answer_bank": {
            "candidate": {
                "full_name": "Akhilesh Arunkumar Kumbhar",
                "legal_first_name": "Akhilesh Arunkumar",
                "legal_last_name": "Kumbhar",
                "email": "akhilesh@example.com",
            }
        },
    }


def test_autopilot_arms_and_serves_matching_context(tmp_path) -> None:
    service = AutofillAutopilotService(state_path=str(tmp_path / "autopilot.json"))

    armed = service.arm(
        AutofillAutopilotArmRequest(
            url="https://jobs.example.com/apply/junior-data-scientist-123",
            apply_plan=sample_apply_plan(),
            open_browser=False,
        )
    )

    assert armed.armed is True
    context = service.context(
        AutofillAutopilotContextRequest(
            url="https://jobs.example.com/apply/junior-data-scientist-123/section/1",
            page_title="Junior Data Scientist",
            page_text="Example Robotics is hiring a Junior Data Scientist.",
        )
    )
    assert context.enabled is True
    assert context.task_id == armed.task_id
    assert context.apply_plan["job"]["company"] == "Example Robotics"

    recorded = service.record_result(
        AutofillAutopilotResultRequest(
            task_id=armed.task_id,
            url=context.apply_plan["job"]["official_url"],
            filled_count=4,
            total_fields=8,
        )
    )
    assert recorded.recorded is True


def test_autopilot_refuses_unrelated_page(tmp_path) -> None:
    service = AutofillAutopilotService(state_path=str(tmp_path / "autopilot.json"))
    service.arm(
        AutofillAutopilotArmRequest(
            url="https://jobs.example.com/apply/junior-data-scientist-123",
            apply_plan=sample_apply_plan(),
            open_browser=False,
        )
    )

    context = service.context(
        AutofillAutopilotContextRequest(
            url="https://totally-different.example.org/apply",
            page_title="Account Manager",
            page_text="A different company and role.",
        )
    )

    assert context.enabled is False
