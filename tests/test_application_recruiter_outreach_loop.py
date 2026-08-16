import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_application_loop_service
from app.main import app
from app.schemas.application_loop import (
    ApplicationLoopBatchImportRequest,
    ApplicationLoopOutreachBatchRequest,
    ApplicationLoopOutreachSentRequest,
    ApplicationLoopOutreachUpdateRequest,
    ApplicationLoopTransitionRequest,
)
from app.services.application_loop_service import ApplicationLoopService, InvalidApplicationLoopTransition
from app.services.recruiter_outreach_batch_service import RecruiterOutreachBatchService


class FakeClaudeMessages:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        request = json.loads(kwargs["messages"][0]["content"])
        notes = [
            {
                "loop_id": job["loop_id"],
                "note": (
                    f"Hi, I applied for the {job['role']} role at {job['company']}. "
                    "My Python, SQL, and operational analytics work aligns with the role, "
                    "and I would value connecting."
                ),
            }
            for job in request["jobs"]
        ]
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps({"notes": notes}))],
            usage=SimpleNamespace(
                input_tokens=900,
                output_tokens=180,
                cache_creation_input_tokens=400,
                cache_read_input_tokens=0,
            ),
        )


class FakeClaudeClient:
    def __init__(self) -> None:
        self.messages = FakeClaudeMessages()


def _submitted_service(tmp_path, monkeypatch, *, count=2):
    monkeypatch.setenv("CAREER_SITE_AGENT_DB_PATH", str(tmp_path / "outreach.db"))
    client = FakeClaudeClient()
    outreach = RecruiterOutreachBatchService(client=client, model="claude-sonnet-5")
    service = ApplicationLoopService(recruiter_outreach=outreach)
    imported = service.import_batch(
        ApplicationLoopBatchImportRequest.model_validate(
            {
                "items": [
                    {
                        "company": "Northwind Analytics" if index == 0 else "Contoso Health",
                        "role": "Operations Data Analyst" if index == 0 else "Healthcare Data Scientist",
                        "job_url": f"https://careers.example.com/jobs/{index}",
                        "jd_text": "Analyze operational data with Python, SQL, dashboards, and stakeholder reporting. " * 6,
                        "source": "Jobright AI",
                    }
                    for index in range(count)
                ]
            }
        )
    )
    loop_ids = []
    for outcome in imported.outcomes:
        item = outcome.loop_item
        for state in ("fit_checked", "draft_ready", "approved_for_apply"):
            item = service.transition(
                item,
                ApplicationLoopTransitionRequest(target_state=state, actor="agent"),
            )
        item = service.transition(
            item,
            ApplicationLoopTransitionRequest(
                target_state="submitted_confirmed",
                actor="human",
                note="Application submitted manually in the company ATS.",
                human_confirmed_submission=True,
            ),
        )
        service._save_item(item)
        loop_ids.append(item.loop_id)
    return service, client, loop_ids


def test_outreach_batch_uses_one_claude_call_groups_companies_and_reuses_cache(tmp_path, monkeypatch) -> None:
    service, client, loop_ids = _submitted_service(tmp_path, monkeypatch)

    prepared = service.prepare_recruiter_outreach_batch(
        ApplicationLoopOutreachBatchRequest(loop_ids=loop_ids, use_llm=True)
    )

    assert prepared.summary.model_dump() == {
        "requested": 2,
        "companies": 2,
        "ready": 2,
        "cached": 0,
        "llm_calls": 1,
        "failed": 0,
    }
    assert len(client.messages.calls) == 1
    assert [group.company for group in prepared.groups] == ["Northwind Analytics", "Contoso Health"]
    assert all(outcome.loop_item.state == "recruiter_note_ready" for outcome in prepared.outcomes)
    assert all(outcome.outreach.engine == "claude" for outcome in prepared.outcomes)
    assert all("linkedin.com/search/results/people" in outcome.outreach.linkedin_search_url for outcome in prepared.outcomes)
    assert all(len(outcome.outreach.connection_note) <= 300 for outcome in prepared.outcomes)

    cached = service.prepare_recruiter_outreach_batch(
        ApplicationLoopOutreachBatchRequest(loop_ids=loop_ids, use_llm=True)
    )

    assert cached.summary.cached == 2
    assert cached.summary.llm_calls == 0
    assert len(client.messages.calls) == 1


def test_outreach_note_is_editable_but_sent_state_requires_human_confirmation(tmp_path, monkeypatch) -> None:
    service, _, [loop_id] = _submitted_service(tmp_path, monkeypatch, count=1)
    service.prepare_recruiter_outreach_batch(
        ApplicationLoopOutreachBatchRequest(loop_ids=[loop_id], use_llm=False)
    )
    edited = service.update_recruiter_outreach(
        loop_id,
        ApplicationLoopOutreachUpdateRequest(
            recruiter_name="Priya",
            connection_note=(
                "Hi Priya, I applied for the Operations Data Analyst role. My Python, SQL, "
                "and Power BI work aligns with the team, and I would value connecting."
            ),
        ),
    )

    assert edited.outreach.recruiter_name == "Priya"
    assert edited.outreach.engine == "deterministic_fallback"
    with pytest.raises(InvalidApplicationLoopTransition, match="human confirmation"):
        service.mark_recruiter_outreach_sent(
            loop_id,
            ApplicationLoopOutreachSentRequest(
                note="Connection request sent manually on LinkedIn.",
                human_confirmed_sent=False,
            ),
        )

    sent = service.mark_recruiter_outreach_sent(
        loop_id,
        ApplicationLoopOutreachSentRequest(
            note="Connection request sent manually on LinkedIn.",
            human_confirmed_sent=True,
        ),
    )
    assert sent.loop_item.state == "outreach_done"
    assert sent.outreach.status == "sent"
    assert sent.outreach.sent_at


def test_outreach_api_prepares_updates_and_records_only_manual_send(tmp_path, monkeypatch) -> None:
    service, _, [loop_id] = _submitted_service(tmp_path, monkeypatch, count=1)
    app.dependency_overrides[get_application_loop_service] = lambda: service
    try:
        client = TestClient(app)
        prepared = client.post(
            "/application-loop/recruiter-outreach/batches",
            json={"loop_ids": [loop_id], "use_llm": False},
        )
        updated = client.put(
            f"/application-loop/items/{loop_id}/recruiter-outreach",
            json={
                "recruiter_name": "Jordan",
                "connection_note": (
                    "Hi Jordan, I applied for the Operations Data Analyst role and would value "
                    "connecting about the team's analytics work."
                ),
            },
        )
        rejected = client.post(
            f"/application-loop/items/{loop_id}/recruiter-outreach/sent",
            json={
                "note": "Connection request sent manually.",
                "human_confirmed_sent": False,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert prepared.status_code == 200
    assert prepared.json()["summary"]["llm_calls"] == 0
    assert updated.status_code == 200
    assert updated.json()["outreach"]["recruiter_name"] == "Jordan"
    assert rejected.status_code == 409
