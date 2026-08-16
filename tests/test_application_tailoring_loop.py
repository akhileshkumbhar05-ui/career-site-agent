from pathlib import Path

from fastapi.testclient import TestClient

from app.dependencies import get_application_loop_service
from app.main import app
from app.schemas.application_loop import (
    ApplicationLoopBatchImportRequest,
    ApplicationLoopFitGateRunRequest,
    ApplicationLoopTailoringApproveRequest,
    ApplicationLoopTailoringDraftRequest,
    ApplicationLoopTailoringExportRequest,
)
from app.schemas.resume import TailoringPreferences
from app.schemas.tailoring_review import (
    TailoringDraftBullet,
    TailoringDraftProject,
    TailoringDraftPublication,
    TailoringDraftResponse,
    TailoringFinalizeResponse,
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
    def __init__(self, output_dir: Path) -> None:
        self.created = []
        self.approved = []
        self.finalized = []
        self.drafts = {}
        self.output_dir = output_dir

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

    def finalize(self, payload):
        self.finalized.append(payload)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        docx_path = self.output_dir / f"{payload.draft_id}.docx"
        pdf_path = self.output_dir / f"{payload.draft_id}.pdf"
        packet_path = self.output_dir / "application_packet"
        packet_path.mkdir(exist_ok=True)
        apply_plan_path = packet_path / "apply_plan.json"
        jd_path = packet_path / "job_description.txt"
        cover_letter_path = packet_path / "cover_letter.txt"
        docx_path.write_bytes(b"test docx")
        apply_plan_path.write_text("{}", encoding="utf-8")
        jd_path.write_text("Saved job description", encoding="utf-8")
        files_written = [str(docx_path), str(apply_plan_path), str(jd_path)]
        if payload.cover_letter_accepted and payload.cover_letter_text.strip():
            cover_letter_path.write_text(payload.cover_letter_text, encoding="utf-8")
            files_written.append(str(cover_letter_path))
        if payload.render_pdf:
            pdf_path.write_bytes(b"%PDF test")
            files_written.append(str(pdf_path))
        return TailoringFinalizeResponse(
            draft_id=payload.draft_id,
            quality_passed=True,
            quality_checks=[{"name": "grounded_metrics", "passed": True}],
            docx_ready=True,
            pdf_ready=payload.render_pdf,
            docx_download_path=f"/autofill/tailoring/download/{payload.draft_id}/docx",
            pdf_download_path=(
                f"/autofill/tailoring/download/{payload.draft_id}/pdf"
                if payload.render_pdf
                else ""
            ),
            prepared_resume_docx_path=str(docx_path),
            prepared_resume_pdf_path=str(pdf_path) if payload.render_pdf else "",
            prepared_apply_plan_path=str(apply_plan_path),
            packet_folder_path=str(packet_path),
            jd_path=str(jd_path),
            apply_url="https://jobs.example.com/tailor-data-analyst",
            cover_letter_path=(
                str(cover_letter_path)
                if payload.cover_letter_accepted and payload.cover_letter_text.strip()
                else ""
            ),
            files_written=files_written,
            message="Files ready.",
        )

def _service(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_SITE_AGENT_DB_PATH", str(tmp_path / "tailoring_loop.db"))
    tailoring = FakeTailoringReview(tmp_path / "exports")
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


def _approved_memory_source(service, loop_id: str):
    service.create_tailoring_draft(loop_id, ApplicationLoopTailoringDraftRequest())
    revised = service.create_tailoring_draft(
        loop_id,
        ApplicationLoopTailoringDraftRequest(
            revision_reason="Expand both research papers with five honest data-analysis bullets.",
            preferences=TailoringPreferences(
                preset="technical_depth",
                rewrite_intensity="strong",
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
    service.approve_tailoring_draft(
        loop_id,
        _review_payload(revised.draft.draft_id),
    )
    return revised


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


def test_tailoring_memory_learns_only_from_approved_similar_roles(tmp_path, monkeypatch) -> None:
    service, _, loop_id = _service(tmp_path, monkeypatch)
    _approved_memory_source(service, loop_id)

    memory = service.tailoring_memory(
        "Senior Operations Data Analyst",
        exclude_loop_id="new-loop-item",
    )
    unrelated = service.tailoring_memory("Computer Vision Engineer")

    assert memory.available is True
    assert memory.role_family == "data_analytics"
    assert memory.approved_sample_count == 1
    assert memory.correction_count == 2
    assert memory.recommended_preferences.preset == "technical_depth"
    assert memory.recommended_preferences.rewrite_intensity == "strong"
    assert memory.recommended_preferences.bullet_counts.experience_per_role == 4
    assert memory.recommended_preferences.bullet_counts.projects_per_project == 3
    assert memory.recommended_preferences.bullet_counts.research_per_paper == 5
    assert "Expand both research papers" in memory.learned_instructions[0]
    assert "past approved corrections" in memory.recommended_preferences.custom_instructions
    assert len(memory.fingerprint) == 64
    assert unrelated.available is False
    assert unrelated.approved_sample_count == 0


def test_tailoring_memory_api_and_draft_provenance(tmp_path, monkeypatch) -> None:
    service, tailoring, source_loop_id = _service(tmp_path, monkeypatch)
    _approved_memory_source(service, source_loop_id)
    imported = service.import_batch(
        ApplicationLoopBatchImportRequest.model_validate(
            {
                "items": [
                    {
                        "company": "Memory Co",
                        "role": "Business Intelligence Analyst",
                        "job_url": "https://jobs.example.com/memory-bi-analyst",
                        "jd_text": (
                            "Company: Memory Co\nRole: Business Intelligence Analyst\n"
                            "Analyze operational data with Python and SQL, build Power BI dashboards, "
                            "and communicate evidence-backed recommendations to business stakeholders."
                        ),
                    }
                ]
            }
        )
    )
    target_loop_id = imported.outcomes[0].loop_item.loop_id
    service.run_fit_gate(ApplicationLoopFitGateRunRequest(loop_ids=[target_loop_id]))

    app.dependency_overrides[get_application_loop_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.get(
            "/application-loop/tailoring-memory",
            params={"role": "Business Intelligence Analyst", "exclude_loop_id": target_loop_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    memory = response.json()
    created = service.create_tailoring_draft(
        target_loop_id,
        ApplicationLoopTailoringDraftRequest(
            preferences=TailoringPreferences.model_validate(memory["recommended_preferences"]),
            preference_memory_fingerprint=memory["fingerprint"],
        ),
    )

    reference = created.loop_item.tailoring_draft
    assert reference.preference_memory_fingerprint == memory["fingerprint"]
    assert reference.preference_memory_role_family == "data_analytics"
    assert reference.preference_memory_source_count == 1
    assert reference.preferences.bullet_counts.research_per_paper == 5
    assert tailoring.created[-1].tailoring_preferences.preset == "technical_depth"
    assert "using learned defaults" in created.loop_item.history[-1].note


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


def test_export_handoff_requires_approval_and_explicit_human_confirmation(tmp_path, monkeypatch) -> None:
    service, tailoring, loop_id = _service(tmp_path, monkeypatch)
    draft = service.create_tailoring_draft(loop_id, ApplicationLoopTailoringDraftRequest())

    try:
        service.export_approved_tailoring(
            loop_id,
            ApplicationLoopTailoringExportRequest(human_confirmed_export=True),
        )
    except InvalidApplicationLoopTransition as exc:
        assert "Approve the draft first" in str(exc)
    else:
        raise AssertionError("An unapproved draft must not generate files.")

    service.approve_tailoring_draft(loop_id, _review_payload(draft.draft.draft_id))
    try:
        service.export_approved_tailoring(loop_id, ApplicationLoopTailoringExportRequest())
    except InvalidApplicationLoopTransition as exc:
        assert "explicit human confirmation" in str(exc)
    else:
        raise AssertionError("Export without human confirmation must be rejected.")

    assert tailoring.finalized == []


def test_export_handoff_uses_approved_selection_and_invalidates_on_revision(tmp_path, monkeypatch) -> None:
    service, tailoring, loop_id = _service(tmp_path, monkeypatch)
    draft = service.create_tailoring_draft(loop_id, ApplicationLoopTailoringDraftRequest())
    approval = _review_payload(draft.draft.draft_id)
    service.approve_tailoring_draft(loop_id, approval)

    exported = service.export_approved_tailoring(
        loop_id,
        ApplicationLoopTailoringExportRequest(
            output_root_override=str(tmp_path / "chosen-resume-root"),
            render_pdf=True,
            human_confirmed_export=True,
        ),
    )

    assert len(tailoring.finalized) == 1
    finalized_payload = tailoring.finalized[0]
    assert finalized_payload.model_dump(exclude={"output_root_override", "render_pdf"}) == (
        approval.model_dump(exclude={"approval_note"})
    )
    assert finalized_payload.output_root_override == str(tmp_path / "chosen-resume-root")
    assert exported.loop_item.state == "approved_for_apply"
    assert exported.handoff.version == 1
    assert exported.handoff.docx_ready is True
    assert exported.handoff.pdf_ready is True
    assert exported.handoff.quality_passed is True
    assert Path(exported.handoff.prepared_resume_docx_path).exists()
    assert service.get_tailoring_export(loop_id).handoff == exported.handoff
    assert service.download_tailoring_export(loop_id, "docx").exists()
    assert service.download_tailoring_export(loop_id, "pdf").exists()
    assert exported.loop_item.history[-1].to_state == "approved_for_apply"
    assert "Export handoff v1" in exported.loop_item.history[-1].note

    revised = service.create_tailoring_draft(
        loop_id,
        ApplicationLoopTailoringDraftRequest(
            revision_reason="Strengthen the research evidence before exporting again."
        ),
    )
    assert revised.loop_item.export_handoff is None
    assert revised.loop_item.tailoring_approval is None


def test_application_export_api_generates_reopens_and_downloads(tmp_path, monkeypatch) -> None:
    service, _, loop_id = _service(tmp_path, monkeypatch)
    draft = service.create_tailoring_draft(loop_id, ApplicationLoopTailoringDraftRequest())
    service.approve_tailoring_draft(loop_id, _review_payload(draft.draft.draft_id))
    app.dependency_overrides[get_application_loop_service] = lambda: service
    try:
        client = TestClient(app)
        rejected = client.post(
            f"/application-loop/items/{loop_id}/tailoring/export",
            json={"render_pdf": True},
        )
        exported = client.post(
            f"/application-loop/items/{loop_id}/tailoring/export",
            json={"render_pdf": True, "human_confirmed_export": True},
        )
        reopened = client.get(f"/application-loop/items/{loop_id}/tailoring/export")
        docx = client.get(f"/application-loop/items/{loop_id}/tailoring/download/docx")
        pdf = client.get(f"/application-loop/items/{loop_id}/tailoring/download/pdf")
    finally:
        app.dependency_overrides.clear()

    assert rejected.status_code == 409
    assert exported.status_code == 200
    assert exported.json()["handoff"]["pdf_ready"] is True
    assert reopened.status_code == 200
    assert reopened.json()["handoff"]["version"] == 1
    assert docx.status_code == 200
    assert ".docx" in docx.headers["content-disposition"]
    assert pdf.status_code == 200


def test_export_handoff_can_generate_docx_without_pdf(tmp_path, monkeypatch) -> None:
    service, _, loop_id = _service(tmp_path, monkeypatch)
    draft = service.create_tailoring_draft(loop_id, ApplicationLoopTailoringDraftRequest())
    service.approve_tailoring_draft(loop_id, _review_payload(draft.draft.draft_id))

    exported = service.export_approved_tailoring(
        loop_id,
        ApplicationLoopTailoringExportRequest(
            render_pdf=False,
            human_confirmed_export=True,
        ),
    )

    assert exported.handoff.docx_ready is True
    assert exported.handoff.pdf_ready is False
    assert exported.handoff.pdf_download_path == ""
    try:
        service.download_tailoring_export(loop_id, "pdf")
    except FileNotFoundError as exc:
        assert "PDF file is not available" in str(exc)
    else:
        raise AssertionError("A DOCX-only handoff must not expose a PDF download.")
