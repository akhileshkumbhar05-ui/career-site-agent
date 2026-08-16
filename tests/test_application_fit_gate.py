from fastapi.testclient import TestClient

from app.dependencies import get_application_loop_service
from app.main import app
from app.schemas.application_loop import (
    ApplicationLoopBatchImportRequest,
    ApplicationLoopFitGateRunRequest,
    ApplicationLoopFitOverrideRequest,
    ApplicationLoopJDUpdateRequest,
)
from app.services.application_loop_service import ApplicationLoopService


class FakeMatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool, bool]] = []

    def analyze(self, job, *, use_llm=True, force_refresh=False):
        company = job["company"]
        self.calls.append((company, use_llm, force_refresh))
        base = {
            "one_line_reason": f"Grounded fit result for {company}.",
            "strengths": ["Matched skill: Python", "Location accepted under relocation preferences."],
            "gaps": ["Domain context needs review."],
            "risks": [],
            "suggested_actions": ["Review the full JD."],
            "sponsorship_note": "No obvious sponsorship blocker found.",
            "years_required": 1.0,
            "target_role_key": "data_analyst",
            "quality_gate_decision": "pass",
            "components": {"required_skills": 88, "preferred_skills": 72},
            "deterministic_score": 81,
            "cache_hit": False,
        }
        if company == "Apply Co":
            return {
                **base,
                "score": 90,
                "verdict": "strong_match",
                "worth_applying": True,
                "scoring_mode": "llm",
                "llm_provider": "anthropic",
                "llm_model": "configured-sonnet",
            }
        if company == "Skip Co":
            return {
                **base,
                "score": 40,
                "verdict": "skip",
                "worth_applying": False,
                "scoring_mode": "deterministic_fallback",
                "risks": ["Work authorization blocker: company does not provide visa sponsorship."],
            }
        return {
            **base,
            "score": 70,
            "verdict": "review",
            "worth_applying": False,
            "scoring_mode": "deterministic_fallback",
            "quality_gate_decision": "review",
        }


def _service(tmp_path, monkeypatch) -> tuple[ApplicationLoopService, FakeMatcher]:
    monkeypatch.setenv("CAREER_SITE_AGENT_DB_PATH", str(tmp_path / "fit_gate.db"))
    matcher = FakeMatcher()
    return ApplicationLoopService(matcher=matcher), matcher


def _jd(company: str) -> str:
    return (
        f"Company: {company}\nRole: Data Analyst\n"
        "Analyze operational data with Python and SQL, build dashboards, and communicate findings. "
        "This junior role requests one year of relevant experience in the United States."
    )


def _import(service: ApplicationLoopService, companies: list[str], *, include_jd: bool = True):
    return service.import_batch(
        ApplicationLoopBatchImportRequest.model_validate(
            {
                "items": [
                    {
                        "company": company,
                        "role": "Data Analyst",
                        "job_url": f"https://jobs.example.com/{company.lower().replace(' ', '-')}-analyst",
                        "jd_text": _jd(company) if include_jd else "",
                    }
                    for company in companies
                ]
            }
        )
    )


def test_fit_gate_persists_decisions_states_and_cached_reuse(tmp_path, monkeypatch) -> None:
    service, matcher = _service(tmp_path, monkeypatch)
    imported = _import(service, ["Apply Co", "Maybe Co", "Skip Co"])
    ids = [outcome.loop_item.loop_id for outcome in imported.outcomes if outcome.loop_item]

    result = service.run_fit_gate(ApplicationLoopFitGateRunRequest(loop_ids=ids, use_llm=True))

    assert result.summary.model_dump() == {
        "requested": 3,
        "evaluated": 3,
        "cached": 0,
        "needs_jd": 0,
        "apply": 1,
        "maybe": 1,
        "skip": 1,
        "llm_calls": 1,
        "failed": 0,
    }
    assert [outcome.result.decision for outcome in result.outcomes if outcome.result] == ["apply", "maybe", "skip"]
    assert [service.get_item(loop_id).state for loop_id in ids] == ["fit_checked", "fit_checked", "skipped"]
    assert service.get_item(ids[0]).fit_gate.llm_model == "configured-sonnet"
    assert service.get_item(ids[0]).fit_gate.skills_fit_note.startswith("Required skills score 88%")

    reused = service.run_fit_gate(ApplicationLoopFitGateRunRequest(loop_ids=ids, use_llm=True))
    assert [outcome.status for outcome in reused.outcomes] == ["cached", "cached", "cached"]
    assert reused.summary.llm_calls == 0
    assert len(matcher.calls) == 3


def test_fit_gate_needs_a_full_jd_without_spending_a_model_call(tmp_path, monkeypatch) -> None:
    service, matcher = _service(tmp_path, monkeypatch)
    imported = _import(service, ["Needs JD Co"], include_jd=False)
    loop_id = imported.outcomes[0].loop_item.loop_id

    pending = service.run_fit_gate(ApplicationLoopFitGateRunRequest(loop_ids=[loop_id]))

    assert pending.summary.needs_jd == 1
    assert pending.outcomes[0].result.evaluation_status == "needs_jd"
    assert service.get_item(loop_id).state == "imported"
    assert matcher.calls == []

    service.update_jd(loop_id, ApplicationLoopJDUpdateRequest(jd_text=_jd("Needs JD Co")))
    complete = service.run_fit_gate(ApplicationLoopFitGateRunRequest(loop_ids=[loop_id]))
    assert complete.summary.evaluated == 1
    assert complete.outcomes[0].result.evaluation_status == "complete"


def test_human_override_can_restore_a_skip_without_another_model_call(tmp_path, monkeypatch) -> None:
    service, matcher = _service(tmp_path, monkeypatch)
    imported = _import(service, ["Skip Co"])
    loop_id = imported.outcomes[0].loop_item.loop_id
    service.run_fit_gate(ApplicationLoopFitGateRunRequest(loop_ids=[loop_id]))

    restored = service.override_fit_gate(
        loop_id,
        ApplicationLoopFitOverrideRequest(
            decision="apply",
            note="The posting confirms OPT eligibility in a recruiter-provided clarification.",
        ),
    )

    assert restored.state == "fit_checked"
    assert restored.fit_gate.decision == "apply"
    assert restored.fit_gate.original_decision == "skip"
    assert restored.fit_gate.overridden is True
    assert restored.history[-1].actor == "human"
    assert len(matcher.calls) == 1


def test_fit_gate_api_runs_and_accepts_a_human_override(tmp_path, monkeypatch) -> None:
    service, _ = _service(tmp_path, monkeypatch)
    imported = _import(service, ["Apply Co"])
    loop_id = imported.outcomes[0].loop_item.loop_id
    app.dependency_overrides[get_application_loop_service] = lambda: service
    try:
        client = TestClient(app)
        gate = client.post("/application-loop/fit-gate", json={"loop_ids": [loop_id], "use_llm": True})
        override = client.post(
            f"/application-loop/items/{loop_id}/fit-override",
            json={"decision": "maybe", "note": "I want to inspect the team scope before tailoring."},
        )
    finally:
        app.dependency_overrides.clear()

    assert gate.status_code == 200
    assert gate.json()["summary"]["apply"] == 1
    assert override.status_code == 200
    assert override.json()["fit_gate"]["decision"] == "maybe"


def test_seniority_note_accepts_numeric_strings() -> None:
    note = ApplicationLoopService._seniority_note({"years_required": "2.5", "risks": []})

    assert note == "The posting appears to require 2.5 years of experience."
