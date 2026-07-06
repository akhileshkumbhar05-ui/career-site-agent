import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.schemas.ats_autofill import AutofillContextRequest
from app.schemas.resume import ResumeTailorResponse, TailoringPreferences
from app.schemas.tailoring_review import (
    TailoringBulletDecision,
    TailoringDraftRequest,
    TailoringFinalizeRequest,
)
from app.services.application_packet_export_service import ApplicationPacketExportService
from app.services.application_packet_service import ApplicationPacketService
from app.services.ats_autofill_service import ATSAutofillService
from app.services.autofill_context_service import AutofillContextService
from app.services.decision_service import DecisionService
from app.services.jd_parser_service import JDParserService
from app.services.job_quality_gate_service import JobQualityGateService
from app.services.scoring_service import ScoringService
from app.services.tailoring_review_service import TailoringReviewService


class _ReviewTailorer:
    def tailor(self, payload):
        return ResumeTailorResponse(
            job_id=payload.job_id,
            resume_version=payload.resume_version,
            source_resume_version=payload.resume_version,
            tailored_resume_version=f"{payload.job_id}_tailored_v1",
            tailored_score=max(82, payload.current_score),
            selected_project_ids=["careersite_agent", "erev_copilot"],
            changes_summary=["Claude draft prepared for review."],
            summary_variant_key="data_analyst",
            summary_text="Data analyst with verified Python, SQL, reporting, and operational analytics experience.",
            rewritten_bullets=[
                {
                    "section": "project",
                    "item_id": "careersite_agent",
                    "project_id": "careersite_agent",
                    "original": "Built a human-in-the-loop career application system.",
                    "rewritten": (
                        "Improved human-in-the-loop analytics workflow preparation, as evidenced by "
                        "Python and FastAPI services, by building structured review and packet-generation logic."
                    ),
                }
            ],
            skill_gaps=["SAS"],
            connection_note="Interested in the Operations Data Analyst role.",
            cover_letter_text=(
                "Dear hiring team,\n\n"
                "I am interested in this Operations Data Analyst role because it aligns with my Python, SQL, "
                "Power BI, and operational analytics experience."
            ),
        )


def _service(tmp_path):
    context = AutofillContextService(
        autofill=ATSAutofillService(apply_plan_roots=[str(tmp_path / "packets")]),
        parser=JDParserService(),
        scorer=ScoringService(),
        tailorer=_ReviewTailorer(),
        decider=DecisionService(),
        quality_gate=JobQualityGateService(),
        packet_builder=ApplicationPacketService(),
        packet_exporter=ApplicationPacketExportService(),
    )
    return TailoringReviewService(
        context=context,
        draft_dir=str(tmp_path / "drafts"),
        audit_path=str(tmp_path / "audit.jsonl"),
    )


def _draft(service):
    return service.create_draft(
        TailoringDraftRequest(
            url="https://careers.example.com/jobs/17893342-operations-data-analyst",
            page_title="Operations Data Analyst | Example Bank",
            page_text="""
            Operations Data Analyst
            Responsibilities include collecting, analyzing, and visualizing operational data,
            preparing reports, improving business processes, and communicating recommendations.
            Requirements: Python, SQL, Tableau, reporting, analytics, and stakeholder communication.
            One to two years of analytics experience. Location: Las Vegas, Nevada, United States.
            """,
            company="Example Bank",
            role="Operations Data Analyst",
            force_prepare=True,
            render_pdf=False,
            tailoring_preferences=TailoringPreferences(preset="business_impact"),
        )
    )


def test_preview_creates_review_draft_without_resume_artifacts(tmp_path):
    service = _service(tmp_path)

    draft = _draft(service)

    assert draft.company == "Example Bank"
    assert draft.bullets[0].proposed.startswith("Improved human-in-the-loop analytics")
    assert [project.project_id for project in draft.projects] == ["careersite_agent", "erev_copilot"]
    assert "Akhilesh Arunkumar Kumbhar" in draft.resume_preview_html
    assert "CareerSite Agent" in draft.resume_preview_html
    assert not list(tmp_path.rglob("*.docx"))
    assert not list(tmp_path.rglob("*.pdf"))
    assert Path(tmp_path / "drafts" / f"{draft.draft_id}.json").exists()


def test_preview_honors_project_and_research_emphasis(tmp_path):
    service = _service(tmp_path)

    draft = service.create_draft(
        TailoringDraftRequest(
            url="https://careers.example.com/jobs/17893342-operations-data-analyst",
            page_title="Operations Data Analyst | Example Bank",
            page_text="""
            Operations Data Analyst
            Responsibilities include collecting, analyzing, and visualizing operational data,
            preparing reports, improving business processes, and communicating recommendations.
            Requirements: Python, SQL, Tableau, reporting, analytics, and stakeholder communication.
            One to two years of analytics experience. Location: Las Vegas, Nevada, United States.
            """,
            company="Example Bank",
            role="Operations Data Analyst",
            force_prepare=True,
            render_pdf=False,
            tailoring_preferences=TailoringPreferences(
                preset="technical_depth",
                emphasis=["summary", "experience", "skills", "research_papers"],
            ),
        )
    )

    assert draft.projects == []
    assert [item.title for item in draft.publications] == [
        "Contributions of Extended-Range Electric Vehicles to Electrified Miles, Emissions, and Transportation Cost Reduction",
        "Applications of ML and Data Science in Healthcare - A Survey",
    ]
    refreshed = service.render_preview(
        TailoringFinalizeRequest(
            draft_id=draft.draft_id,
            summary_text=draft.summary_proposed,
            bullets=[],
            project_ids=[],
            publication_ids=[draft.publications[0].publication_id],
            render_pdf=False,
        )
    )
    assert "Key Projects" not in refreshed.resume_preview_html
    assert "Research & Publications" in refreshed.resume_preview_html
    assert "286.1 million vehicles" in refreshed.resume_preview_html
    assert "3,262.80 billion annual miles" in refreshed.resume_preview_html


def test_finalize_renders_after_review_and_exposes_docx_download(tmp_path):
    service = _service(tmp_path)
    draft = _draft(service)

    result = service.finalize(
        TailoringFinalizeRequest(
            draft_id=draft.draft_id,
            summary_accepted=True,
            summary_text=draft.summary_proposed,
            bullets=[
                TailoringBulletDecision(
                    bullet_id=draft.bullets[0].bullet_id,
                    accepted=False,
                    text=draft.bullets[0].original,
                )
            ],
            project_ids=["erev_copilot", "careersite_agent"],
            publication_ids=[],
            output_root_override=str(tmp_path / "final"),
            render_pdf=False,
        )
    )

    assert result.docx_ready is True
    assert result.pdf_ready is False
    assert Path(result.prepared_resume_docx_path).exists()
    assert service.download_path(draft.draft_id, "docx") == Path(result.prepared_resume_docx_path)
    assert result.prepared_apply_plan_path.endswith("apply_plan.json")
    assert result.apply_url == "https://careers.example.com/jobs/17893342-operations-data-analyst"
    audit = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "draft_created" in audit
    assert "draft_finalized" in audit


def test_finalize_persists_reviewed_cover_letter_into_apply_plan(tmp_path):
    service = _service(tmp_path)
    draft = service.create_draft(
        TailoringDraftRequest(
            url="https://careers.example.com/jobs/17893342-operations-data-analyst",
            page_title="Operations Data Analyst | Example Bank",
            page_text="""
            Operations Data Analyst
            Responsibilities include collecting, analyzing, and visualizing operational data,
            preparing reports, improving business processes, and communicating recommendations.
            Requirements: Python, SQL, Tableau, reporting, analytics, and stakeholder communication.
            One to two years of analytics experience. Location: Las Vegas, Nevada, United States.
            """,
            company="Example Bank",
            role="Operations Data Analyst",
            force_prepare=True,
            render_pdf=False,
            tailoring_preferences=TailoringPreferences(
                preset="business_impact",
                include_cover_letter=True,
            ),
        )
    )

    result = service.finalize(
        TailoringFinalizeRequest(
            draft_id=draft.draft_id,
            summary_accepted=True,
            summary_text=draft.summary_proposed,
            bullets=[],
            project_ids=["careersite_agent"],
            cover_letter_text=draft.cover_letter_text,
            output_root_override=str(tmp_path / "final_cover"),
            render_pdf=False,
        )
    )

    apply_plan = json.loads(Path(result.prepared_apply_plan_path).read_text(encoding="utf-8"))
    assert result.cover_letter_path
    assert Path(result.cover_letter_path).exists()
    assert apply_plan["cover_letter"]["requested"] is True
    assert "Operations Data Analyst" in apply_plan["cover_letter"]["body"]


def test_finalize_allows_research_without_projects(tmp_path):
    service = _service(tmp_path)
    draft = service.create_draft(
        TailoringDraftRequest(
            url="https://careers.example.com/jobs/17893342-operations-data-analyst",
            page_title="Operations Data Analyst | Example Bank",
            page_text="""
            Operations Data Analyst
            Responsibilities include collecting, analyzing, and visualizing operational data,
            preparing reports, improving business processes, and communicating recommendations.
            Requirements: Python, SQL, Tableau, reporting, analytics, and stakeholder communication.
            One to two years of analytics experience. Location: Las Vegas, Nevada, United States.
            """,
            company="Example Bank",
            role="Operations Data Analyst",
            force_prepare=True,
            render_pdf=False,
            tailoring_preferences=TailoringPreferences(
                preset="technical_depth",
                emphasis=["summary", "experience", "skills", "research_papers"],
            ),
        )
    )

    result = service.finalize(
        TailoringFinalizeRequest(
            draft_id=draft.draft_id,
            summary_accepted=True,
            summary_text=draft.summary_proposed,
            bullets=[],
            project_ids=[],
            publication_ids=[draft.publications[0].publication_id],
            output_root_override=str(tmp_path / "final_research"),
            render_pdf=False,
        )
    )

    html = Path(result.prepared_resume_docx_path).with_suffix(".html").read_text(encoding="utf-8")
    assert "Key Projects" not in html
    assert "Research & Publications" in html
    assert "Extended-Range Electric Vehicles" in html
    assert "573.9 Mt CO2 savings" in html


def test_preview_honors_bullet_count_controls(tmp_path):
    service = _service(tmp_path)
    draft = service.create_draft(
        TailoringDraftRequest(
            url="https://careers.example.com/jobs/17893342-operations-data-analyst",
            page_title="Operations Data Analyst | Example Bank",
            page_text="""
            Operations Data Analyst
            Responsibilities include collecting, analyzing, and visualizing operational data,
            preparing reports, improving business processes, and communicating recommendations.
            Requirements: Python, SQL, Tableau, reporting, analytics, and stakeholder communication.
            One to two years of analytics experience. Location: Las Vegas, Nevada, United States.
            """,
            company="Example Bank",
            role="Operations Data Analyst",
            force_prepare=True,
            render_pdf=False,
            tailoring_preferences=TailoringPreferences(
                preset="technical_depth",
                emphasis=["summary", "experience", "skills", "research_papers"],
            ),
        )
    )

    refreshed = service.render_preview(
        TailoringFinalizeRequest(
            draft_id=draft.draft_id,
            summary_text=draft.summary_proposed,
            bullets=[],
            project_ids=[],
            publication_ids=[item.publication_id for item in draft.publications],
            bullet_counts={
                "experience_per_role": 1,
                "projects_per_project": 0,
                "research_per_paper": 1,
            },
            render_pdf=False,
        )
    )

    html = refreshed.resume_preview_html
    assert "Enabled secure, real-time operational reporting" not in html
    assert "Identified 100-125 mile EREV range" not in html
    assert "Mapped healthcare AI deployment risk" not in html
    assert "Achieved about 70% top-N relevance accuracy" in html
    assert "286.1 million vehicles" in html
    assert "86% reported AI usage" in html


def test_preview_accepts_dynamic_counts_above_old_dropdown_caps(tmp_path):
    service = _service(tmp_path)
    draft = _draft(service)

    refreshed = service.render_preview(
        TailoringFinalizeRequest(
            draft_id=draft.draft_id,
            summary_text=draft.summary_proposed,
            bullets=[],
            project_ids=["careersite_agent"],
            publication_ids=[],
            bullet_counts={
                "experience_per_role": 7,
                "projects_per_project": 9,
                "research_per_paper": 4,
            },
            render_pdf=False,
        )
    )

    html = refreshed.resume_preview_html
    assert "Improved stakeholder understanding of applied AI workflows" in html
    assert "Increased decision consistency across job leads" in html


def test_research_bullet_count_is_per_selected_paper(tmp_path):
    service = _service(tmp_path)
    draft = service.create_draft(
        TailoringDraftRequest(
            url="https://careers.example.com/jobs/17893342-operations-data-analyst",
            page_title="Operations Data Analyst | Example Bank",
            page_text="""
            Operations Data Analyst
            Responsibilities include collecting, analyzing, and visualizing operational data,
            preparing reports, improving business processes, and communicating recommendations.
            Requirements: Python, SQL, Tableau, reporting, analytics, and stakeholder communication.
            One to two years of analytics experience. Location: Las Vegas, Nevada, United States.
            """,
            company="Example Bank",
            role="Operations Data Analyst",
            force_prepare=True,
            render_pdf=False,
            tailoring_preferences=TailoringPreferences(
                preset="technical_depth",
                emphasis=["summary", "experience", "skills", "research_papers"],
            ),
        )
    )

    refreshed = service.render_preview(
        TailoringFinalizeRequest(
            draft_id=draft.draft_id,
            summary_text=draft.summary_proposed,
            bullets=[],
            project_ids=[],
            publication_ids=[item.publication_id for item in draft.publications],
            bullet_counts={
                "experience_per_role": 6,
                "projects_per_project": 0,
                "research_per_paper": 5,
            },
            render_pdf=False,
        )
    )

    html = refreshed.resume_preview_html
    assert "286.1 million vehicles" in html
    assert "86% reported AI usage" in html
    assert "320 billion added electric miles" in html
    assert "80% clinical-trial enrollment failures" in html
    assert "3.6 TWh" in html
    assert "4 evidence categories" in html


def test_finalize_blocks_unsupported_user_metric(tmp_path):
    service = _service(tmp_path)
    draft = _draft(service)

    with pytest.raises(HTTPException) as exc:
        service.finalize(
            TailoringFinalizeRequest(
                draft_id=draft.draft_id,
                summary_text=draft.summary_proposed,
                bullets=[
                    TailoringBulletDecision(
                        bullet_id=draft.bullets[0].bullet_id,
                        accepted=True,
                        text="Improved operational accuracy by 987654%.",
                    )
                ],
                project_ids=["careersite_agent"],
                output_root_override=str(tmp_path / "final"),
                render_pdf=False,
            )
        )

    assert exc.value.status_code == 400
    assert "unsupported metrics" in exc.value.detail.lower()
