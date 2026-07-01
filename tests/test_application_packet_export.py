import json
import os
import shutil
from pathlib import Path

from app.schemas.application_packet import ApplicationPacketExportRequest
from app.services.application_packet_export_service import ApplicationPacketExportService
from app.services.application_packet_service import ApplicationPacketService


def test_application_packet_export_writes_expected_files():
    tmp_path = Path("data/outputs/test_application_packet_export") / str(os.getpid())
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    tmp_path.mkdir(parents=True)

    profile_path = tmp_path / "application_profile.json"
    profile = {
        "candidate": {
            "full_name": "Akhilesh Arunkumar Kumbhar",
            "legal_first_name": "Akhilesh Arunkumar",
            "legal_last_name": "Kumbhar",
            "email": "akhileshkumbhar0405@gmail.com",
            "phone": "+1 (346) 592-3971",
            "city": "Arlington",
            "state": "TX",
            "country": "United States",
            "linkedin": "LinkedIn",
            "github": "GitHub",
        },
        "work_authorization": {
            "authorized_to_work_in_united_states": True,
            "current_status": "F1 OPT",
            "requires_current_sponsorship": False,
            "requires_future_sponsorship": True,
            "standard_explanation": "Currently authorized on F1 OPT.",
        },
        "preferences": {
            "willing_to_relocate": True,
            "salary_filter_enabled": False,
            "target_level": "junior",
        },
        "resume_storage": {
            "root_directory": str(tmp_path / "resumes"),
            "base_resume_pdf": str(tmp_path / "base.pdf"),
        },
        "automation_boundary": {
            "allow_prefill": True,
            "allow_final_submit": False,
            "submit_instruction": "Application portals may be prefilled, but final review and submission must remain manual.",
        },
    }
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    packet_builder = ApplicationPacketService(profile_path=str(profile_path))
    packet = packet_builder.build(
        company="Best Buy",
        role="Associate Decision Scientist, Market Share",
        official_url="https://example.com/job",
        base_score=82,
        tailored_score=88,
        decision="apply_now",
        decision_reason="Strong fit after tailoring.",
        target_role_key="data_scientist",
    )

    exporter = ApplicationPacketExportService()
    response = exporter.export(
        ApplicationPacketExportRequest(
            application_packet=packet,
            output_root_override=str(tmp_path / "packet_override_root"),
            selected_project_ids=["careersite_agent", "otto_recommender", "erev_copilot"],
            changes_summary=["Selected projects for analytics and automation alignment."],
            summary_text="Tailored summary text.",
            jd_text="Job description text.",
            recruiter_subject="Interest in the role",
            recruiter_body="Hi, I am interested.",
        )
    )

    written_paths = [Path(item) for item in response.files_written]
    assert all(path.exists() for path in written_paths)
    assert Path(response.tailored_resume_docx_path).exists()
    assert response.tailored_resume_docx_path.endswith(".docx")
    assert Path(response.tailored_resume_html_path).exists()
    assert Path(response.apply_plan_path).exists()
    assert Path(response.ats_answers_path).exists()
    assert "packet_override_root" in response.company_folder_path
    assert response.intended_tailored_resume_pdf_path.startswith(str(tmp_path / "packet_override_root"))
    assert response.quality_passed is True
    assert any(item["name"] == "section_professional_experience" for item in response.quality_checks)
    assert any(item["name"] == "xyz_bullet_shape" and item["passed"] for item in response.quality_checks)
    assert "final review and submission" in Path(response.checklist_path).read_text(encoding="utf-8").lower()
    assert "Common ATS Answers" in Path(response.checklist_path).read_text(encoding="utf-8")
    assert "Requires Sponsorship Future: Yes" in Path(response.ats_answers_path).read_text(encoding="utf-8")
    assert "Job description text." in Path(response.jd_path).read_text(encoding="utf-8")
    assert "Interest in the role" in Path(response.outreach_path).read_text(encoding="utf-8")
    assert "LinkedIn connection note" in Path(response.outreach_path).read_text(encoding="utf-8")

    apply_plan = json.loads(Path(response.apply_plan_path).read_text(encoding="utf-8"))
    assert apply_plan["human_control"]["allow_final_submit"] is False
    assert apply_plan["resume"]["tailored_resume_path"].startswith(str(tmp_path / "packet_override_root"))
    assert apply_plan["resume"]["tailored_resume_path"].endswith(".docx")
    assert Path(apply_plan["resume"]["tailored_resume_path"]).exists()
    assert apply_plan["resume"]["tailored_resume_docx_path"] == apply_plan["resume"]["tailored_resume_path"]
    assert apply_plan["resume"]["tailored_resume_html_path"].startswith(str(tmp_path / "packet_override_root"))
    assert apply_plan["resume"]["intended_tailored_resume_pdf_path"].endswith(".pdf")
    assert apply_plan["ats_answer_bank"]["candidate"]["legal_first_name"] == "Akhilesh Arunkumar"
    assert apply_plan["ats_answer_bank"]["candidate"]["legal_last_name"] == "Kumbhar"
    assert apply_plan["ats_answer_bank"]["candidate"]["linkedin_url"] == "LinkedIn"
    assert apply_plan["recruiter_outreach"]["searches"]


def test_application_packet_export_filters_skills_and_preserves_evidence_bullets():
    tmp_path = Path("data/outputs/test_application_packet_export_quality") / str(os.getpid())
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    tmp_path.mkdir(parents=True)

    profile_path = tmp_path / "application_profile.json"
    profile = {
        "candidate": {
            "full_name": "Akhilesh Arunkumar Kumbhar",
            "legal_first_name": "Akhilesh Arunkumar",
            "legal_last_name": "Kumbhar",
            "email": "akhileshkumbhar0405@gmail.com",
            "phone": "+1 (346) 592-3971",
            "city": "Arlington",
            "state": "TX",
            "country": "United States",
            "linkedin": "LinkedIn",
            "github": "GitHub",
        },
        "work_authorization": {},
        "preferences": {},
        "resume_storage": {
            "root_directory": str(tmp_path / "resumes"),
            "base_resume_pdf": str(tmp_path / "base.pdf"),
        },
        "automation_boundary": {
            "submit_instruction": "Application portals may be prefilled, but final review and submission must remain manual.",
        },
    }
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    packet = ApplicationPacketService(profile_path=str(profile_path)).build(
        company="Aspire",
        role="Business Analyst",
        official_url="https://example.com/business-analyst",
        base_score=72,
        tailored_score=78,
        decision="manual_review",
        decision_reason="Relevant analytics background, but domain fit needs review.",
        target_role_key="business_analyst",
    )

    response = ApplicationPacketExportService().export(
        ApplicationPacketExportRequest(
            application_packet=packet,
            output_root_override=str(tmp_path / "packet_override_root"),
            selected_project_ids=["otto_recommender"],
            summary_text=(
                "Business Analyst with technical analytics experience across Power BI dashboards, "
                "operational reporting, forecasting, documentation, and workflow improvement."
            ),
            jd_text=(
                "Business Analyst role supporting financial systems, billing operations, "
                "root cause analysis, process documentation, SQL, Excel, and Power BI reporting."
            ),
            rewritten_bullets=[
                {
                    "section": "experience",
                    "item_id": "ai_data_science_engineer_borderless_healthcare_group_bh_mobile_pte_ltd",
                    "original": "Designed three-tier data models and delivered Power BI dashboards via .NET Core APIs.",
                    "rewritten": (
                        "Improved cross-functional reporting visibility, as evidenced by Power BI operational "
                        "dashboards and data models, by supporting process workflows with structured analytics."
                    ),
                }
            ],
        )
    )

    html = Path(response.tailored_resume_html_path).read_text(encoding="utf-8")
    assert "Research & Publications" not in html
    assert "Improved cross-functional reporting visibility" in html
    assert "as evidenced by Power BI operational" in html
    assert "Achieved about 70% top-N relevance accuracy" in html
    assert "Power BI" in html
    assert "MS Excel" in html
    assert "Computer Vision" not in html
    assert "Deep Learning" not in html
    assert "YOLOv8" not in html
    assert "RAG Pipelines" not in html

    metadata = json.loads(Path(response.metadata_path).read_text(encoding="utf-8"))
    selected_skills = json.dumps(metadata["selected_skills"])
    assert "Power BI" in selected_skills
    assert "Computer Vision" not in selected_skills


def test_application_packet_export_explains_selected_publications():
    tmp_path = Path("data/outputs/test_application_packet_export_publications") / str(os.getpid())
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    tmp_path.mkdir(parents=True)

    profile_path = tmp_path / "application_profile.json"
    profile = {
        "candidate": {
            "full_name": "Akhilesh Arunkumar Kumbhar",
            "legal_first_name": "Akhilesh Arunkumar",
            "legal_last_name": "Kumbhar",
            "email": "akhileshkumbhar0405@gmail.com",
            "phone": "+1 (346) 592-3971",
            "city": "Arlington",
            "state": "TX",
            "country": "United States",
            "linkedin": "LinkedIn",
            "github": "GitHub",
        },
        "work_authorization": {},
        "preferences": {},
        "resume_storage": {
            "root_directory": str(tmp_path / "resumes"),
            "base_resume_pdf": str(tmp_path / "base.pdf"),
        },
        "automation_boundary": {
            "submit_instruction": "Application portals may be prefilled, but final review and submission must remain manual.",
        },
    }
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    packet = ApplicationPacketService(profile_path=str(profile_path)).build(
        company="Credit One Bank",
        role="Operations Data Analyst",
        official_url="https://example.com/operations-data-analyst",
        base_score=79,
        tailored_score=82,
        decision="manual_review",
        decision_reason="Relevant analytics background.",
        target_role_key="data_analyst",
    )

    exporter = ApplicationPacketExportService()
    publication_ids = [
        exporter._publication_id(
            {
                "title": "Contributions of Extended-Range Electric Vehicles to Electrified Miles, Emissions, and Transportation Cost Reduction",
                "venue": "Energies (MDPI)",
                "year": "2025",
            }
        ),
        exporter._publication_id(
            {
                "title": "Applications of ML and Data Science in Healthcare - A Survey",
                "venue": "ICTCS 2022",
                "year": "2022",
            }
        ),
    ]
    response = exporter.export(
        ApplicationPacketExportRequest(
            application_packet=packet,
            output_root_override=str(tmp_path / "packet_override_root"),
            selected_project_ids=[],
            auto_select_projects=False,
            selected_publication_ids=publication_ids,
            include_publications=True,
            summary_text="Data analyst with verified research, reporting, and operational analytics experience.",
            jd_text="Operations analyst role requiring research, reporting, Python, SQL, and business process improvement.",
        )
    )

    html = Path(response.tailored_resume_html_path).read_text(encoding="utf-8")
    assert response.quality_passed is True
    assert "Key Projects" not in html
    assert "Research & Publications" in html
    assert "286.1 million vehicles" in html
    assert "573.9 Mt CO2 savings" in html
    assert "2,314 exabytes" in html


def test_application_packet_export_applies_generated_publication_bullets():
    tmp_path = Path("data/outputs/test_application_packet_export_publication_rewrites") / str(os.getpid())
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    tmp_path.mkdir(parents=True)

    profile_path = tmp_path / "application_profile.json"
    profile = {
        "candidate": {
            "full_name": "Akhilesh Arunkumar Kumbhar",
            "legal_first_name": "Akhilesh Arunkumar",
            "legal_last_name": "Kumbhar",
            "email": "akhileshkumbhar0405@gmail.com",
            "phone": "+1 (346) 592-3971",
            "city": "Arlington",
            "state": "TX",
            "country": "United States",
            "linkedin": "LinkedIn",
            "github": "GitHub",
        },
        "work_authorization": {},
        "preferences": {},
        "resume_storage": {
            "root_directory": str(tmp_path / "resumes"),
            "base_resume_pdf": str(tmp_path / "base.pdf"),
        },
        "automation_boundary": {
            "submit_instruction": "Application portals may be prefilled, but final review and submission must remain manual.",
        },
    }
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    packet = ApplicationPacketService(profile_path=str(profile_path)).build(
        company="Credit One Bank",
        role="Operations Data Analyst",
        official_url="https://example.com/operations-data-analyst",
        base_score=79,
        tailored_score=82,
        decision="manual_review",
        decision_reason="Relevant analytics background.",
        target_role_key="data_analyst",
    )
    publication_id = (
        "contributions_of_extended_range_electric_vehicles_to_electrified_miles_emissions_and_transportat"
    )

    response = ApplicationPacketExportService().export(
        ApplicationPacketExportRequest(
            application_packet=packet,
            output_root_override=str(tmp_path / "packet_override_root"),
            selected_project_ids=[],
            selected_publication_ids=[publication_id],
            include_publications=True,
            bullet_counts={
                "experience_per_role": 1,
                "projects_per_project": 0,
                "research_per_paper": 4,
            },
            summary_text="Data analyst with verified research, reporting, and operational analytics experience.",
            jd_text="Operations analyst role requiring research, reporting, Python, SQL, and business process improvement.",
            rewritten_bullets=[
                {
                    "section": "publication",
                    "item_id": publication_id,
                    "publication_id": publication_id,
                    "original": "Source evidence: 3.6 TWh and 0.41 trillion USD are from the EREV paper summary.",
                    "rewritten": (
                        "Quantified fleet-scale battery investment needs, as evidenced by 3.6 TWh and "
                        "0.41 trillion USD CAPEX for 50-mile EREVs, by converting range assumptions "
                        "into battery-capacity and cost-per-mile analytics."
                    ),
                }
            ],
        )
    )

    html = Path(response.tailored_resume_html_path).read_text(encoding="utf-8")
    assert any(
        item["name"] == "rewritten_bullet_1_metrics_supported" and item["passed"]
        for item in response.quality_checks
    )
    assert "3.6 TWh" in html
    assert "0.41 trillion USD" in html
