from fastapi.testclient import TestClient

from app.dependencies import get_application_loop_service
from app.main import app
from app.schemas.application_loop import (
    ApplicationLoopBatchImportRequest,
    ApplicationLoopFitGateRunRequest,
    ApplicationLoopTailoringApproveRequest,
    ApplicationLoopTailoringDraftRequest,
)
from app.schemas.resume import TailoringPreferences
from app.schemas.tailoring_review import (
    TailoringDraftBullet,
    TailoringDraftProject,
    TailoringDraftPublication,
    TailoringDraftResponse,
    TailoringPreviewRenderResponse,
)
from app.services.application_loop_service import (
    ApplicationLoopService,
    InvalidApplicationLoopTransition,
)


class ApplyMatcher:
    def analyze(self, _job, *, use_llm=True, force_refresh=False):
        return {
            "score": 88,
            "verdict": "strong_match",
            "worth_applying": True,
            "one_line_reason": "Strong grounded fit for tailoring.",
            "strengths": ["Python and SQL alignment."],
            "gaps": [],
            "risks": [],
            "suggested_actions": ["Create a tailored draft."],
            "sponsorship_note": "No explicit sponsorship blocker found.",
            "years_required": 1,
            "target_role_key": "data_analyst",
            "quality_gate_decision": "pass",
            "components": {"required_skills": 90, "preferred_skills": 80},
            "deterministic_score": 84,
            "scoring_mode": "llm" if use_llm else "deterministic_fallback",
            "llm_provider": "anthropic" if use_llm else "",
            "llm_model": "claude-sonnet-5" if use_llm else "",
            "cache_hit": False,
        }


class FakeTailoringReview:
    def __init__(self) -> None:
        self.created = []
        self.approved = []
        self.drafts = {}

    def create_draft(self, payload):
        self.created.append(payload)
        version = len(self.created)
        draft = TailoringDraftResponse(
            draft_id=f"{version:032x}",
            company=payload.company,
            role=payload.role,
            target_role_key="data_analyst",
            base_score=82,
            tailored_score=91,
            preferences=payload.tailoring_preferences,
            summary_original="Original evidence-backed summary.",
            summary_proposed="Tailored evidence-backed summary.",
            bullets=[
                TailoringDraftBullet(
                    bullet_id=f"bullet-{version}",
                    section="experience",
                    item_id="experience-one",
                    item_label="Data Analyst",
                    original="Built operational dashboards with verified source evidence.",
                    proposed=(
                        "Improved operational visibility, as evidenced by Power BI dashboards, "
                        "by analyzing service data with Python and SQL."
                    ),
                )
            ],
            projects=[TailoringDraftProject(project_id="project-one", name="Project One")],
            publications=[
                TailoringDraftPublication(
                    publication_id="paper-one",
                    title="Paper One",
                    venue="Research Venue",
                    year="2025",
                )
            ],
            resume_preview_html=f"<html><body>Resume preview v{version}</body></html>",
            message="Draft ready. No files generated.",
            engine="ClaudeTailoringService",
            model="claude-sonnet-5",
            llm_usage={"input_tokens": 1200, "output_tokens": 500},
            claude_call_consumed=True,
        )
        self.drafts[draft.draft_id] = draft
        return draft

    def get_draft(self, draft_id):
        return self.drafts[draft_id]

    def render_preview(self, payload):
        return TailoringPreviewRenderResponse(
            draft_id=payload.draft_id,
            resume_preview_html="<html><body>Reviewed full resume</body></html>",
        )

    def approve_draft(self, payload):
        self.approved.append(payload)
        return TailoringPreviewRenderResponse(
            draft_id=payload.draft_id,
            resume_preview_html="<html><body>Approved full resume</body></html>",
            message="Approved without generating files.",
        )


def _service(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_SITE_AGENT_DB_PATH", str(tmp_path / "tailoring_loop.db"))
    tailoring = FakeTailoringReview()
    service = ApplicationLoopService(matcher=ApplyMatcher(), tailoring_review=tailoring)
    imported = service.import_batch(
        ApplicationLoopBatchImportRequest.model_validate(
            {
                "items": [
                    {
                        "company": "Tailor Co",
                        "role": "Data Analyst",
                        "job_url": "https://jobs.example.com/tailor-data-analyst",
                        "jd_text": (
                            "Company: Tailor Co\nRole: Data Analyst\n"
                            "Analyze operational data with Python and SQL, build Power BI dashboards, "
                            "and communicate evidence-backed recommendations to business stakeholders. "
                            "This early-career position requests one year of relevant experience."
                        ),
                    }
                ]
            }
        )
    )
    loop_id = imported.outcomes[0].loop_item.loop_id
    service.run_fit_gate(ApplicationLoopFitGateRunRequest(loop_ids=[loop_id]))
    return service, tailoring, loop_id


def _review_payload(draft_id: str, *, note: str = "The full resume is grounded and ready for export."):
    return ApplicationLoopTailoringApproveRequest.model_validate(
        {
            "draft_id": draft_id,
            "summary_accepted": True,
            "summary_text": "Tailored evidence-backed summary.",
            "bullets": [{"bullet_id": "bullet-2", "accepted": True, "text": ""}],
            "project_ids": ["project-one"],
            "publication_ids": ["paper-one"],
            "bullet_counts": {
                "experience_per_role": 4,
                "projects_per_project": 3,
                "research_per_paper": 5,
            },
            "approval_note": note,
        }
    )


def test_tailoring_loop_persists_draft_revision_and_approval(tmp_path, monkeypatch) -> None:
    service, tailoring, loop_id = _service(tmp_path, monkeypatch)

    first = service.create_tailoring_draft(
        loop_id,
        ApplicationLoopTailoringDraftRequest(
            preferences=TailoringPreferences(
                emphasis=["summary", "experience", "skills", "research_papers"],
                bullet_counts={
                    "experience_per_role": 3,
                    "projects_per_project": 2,
                    "research_per_paper": 4,
                },
            )
        ),
    )

    assert first.loop_item.state == "draft_ready"
    assert first.loop_item.tailoring_draft.version == 1
    assert first.loop_item.revision_count == 0
    assert first.draft.claude_call_consumed is True
    assert service.get_tailoring_draft(loop_id).draft.draft_id == first.draft.draft_id

    revised = service.create_tailoring_draft(
        loop_id,
        ApplicationLoopTailoringDraftRequest(
            revision_reason="Expand both research papers with five honest data-analysis bullets.",
            preferences=TailoringPreferences(
                preset="technical_depth",
                emphasis=["summary", "experience", "skills", "research_papers"],
                custom_instructions="Prioritize the quantitative analyses in both publications.",
                bullet_counts={
                    "experience_per_role": 4,
                    "projects_per_project": 0,
                    "research_per_paper": 5,
                },
            ),
        ),
    )

    assert revised.loop_item.state == "draft_ready"
    assert revised.loop_item.revision_count == 1
    assert revised.loop_item.tailoring_draft.version == 2
    assert len(revised.loop_item.tailoring_history) == 2
    assert revised.loop_item.history[-2].to_state == "revision_requested"
    assert revised.loop_item.history[-2].note.startswith("Expand both research papers")
    assert tailoring.created[-1].tailoring_preferences.bullet_counts.research_per_paper == 5

    preview = service.render_tailoring_preview(loop_id, _review_payload(revised.draft.draft_id))
    assert "Reviewed full resume" in preview.resume_preview_html

    approved = service.approve_tailoring_draft(loop_id, _review_payload(revised.draft.draft_id))
    assert approved.loop_item.state == "approved_for_apply"
    assert approved.loop_item.tailoring_approval.review.bullet_counts.research_per_paper == 5
    assert approved.loop_item.tailoring_approval.note.startswith("The full resume")
    assert len(tailoring.approved) == 1


def test_revision_requires_a_human_reason(tmp_path, monkeypatch) -> None:
    service, _, loop_id = _service(tmp_path, monkeypatch)
    service.create_tailoring_draft(loop_id, ApplicationLoopTailoringDraftRequest())

    try:
        service.create_tailoring_draft(loop_id, ApplicationLoopTailoringDraftRequest())
    except InvalidApplicationLoopTransition as exc:
        assert "Record what should change" in str(exc)
    else:
        raise AssertionError("A revision without a human reason should be rejected.")


def test_application_tailoring_api_creates_reopens_and_approves(tmp_path, monkeypatch) -> None:
    service, _, loop_id = _service(tmp_path, monkeypatch)
    app.dependency_overrides[get_application_loop_service] = lambda: service
    try:
        client = TestClient(app)
        created = client.post(
            f"/application-loop/items/{loop_id}/tailoring/drafts",
            json={"preferences": {"preset": "business_impact"}},
        )
        reopened = client.get(f"/application-loop/items/{loop_id}/tailoring/draft")
        draft_id = created.json()["draft"]["draft_id"]
        approved = client.post(
            f"/application-loop/items/{loop_id}/tailoring/approve",
            json={
                "draft_id": draft_id,
                "summary_accepted": True,
                "summary_text": "Tailored evidence-backed summary.",
                "bullets": [],
                "project_ids": ["project-one"],
                "publication_ids": ["paper-one"],
                "approval_note": "Reviewed the complete resume preview and accepted the evidence.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert created.status_code == 200
    assert reopened.status_code == 200
    assert approved.status_code == 200
    assert approved.json()["loop_item"]["state"] == "approved_for_apply"
