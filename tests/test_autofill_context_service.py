import json
from pathlib import Path

from app.schemas.ats_autofill import AutofillContextRequest
from app.services.application_packet_export_service import ApplicationPacketExportService
from app.services.application_packet_service import ApplicationPacketService
from app.services.ats_autofill_service import ATSAutofillService
from app.services.autofill_context_service import AutofillContextService
from app.services.decision_service import DecisionService
from app.services.jd_parser_service import JDParserService
from app.services.job_quality_gate_service import JobQualityGateService
from app.services.scoring_service import ScoringService
from app.services.tailoring_service import TailoringService


def build_service(tmp_path, *, profile_path: str | None = None) -> AutofillContextService:
    return AutofillContextService(
        autofill=ATSAutofillService(apply_plan_roots=[str(tmp_path / "autofill_packets")]),
        parser=JDParserService(),
        scorer=ScoringService(),
        tailorer=TailoringService(),
        decider=DecisionService(),
        quality_gate=JobQualityGateService(),
        packet_builder=ApplicationPacketService(profile_path=profile_path or "data/application_profile.json"),
        packet_exporter=ApplicationPacketExportService(),
    )


def write_profile(path, resume_root) -> None:
    path.write_text(
        json.dumps(
            {
                "candidate": {
                    "full_name": "Akhilesh Arunkumar Kumbhar",
                    "legal_first_name": "Akhilesh Arunkumar",
                    "legal_last_name": "Kumbhar",
                    "email": "test@example.com",
                    "phone": "555-0100",
                    "city": "Arlington",
                    "state": "TX",
                    "country": "United States",
                    "linkedin_url": "https://www.linkedin.com/in/test",
                },
                "work_authorization": {
                    "authorized_to_work_in_united_states": True,
                    "requires_current_sponsorship": False,
                    "requires_future_sponsorship": True,
                },
                "preferences": {"willing_to_relocate": True, "target_level": "junior"},
                "resume_storage": {
                    "root_directory": str(resume_root),
                    "base_resume_pdf": str(resume_root / "base.pdf"),
                },
                "automation_boundary": {
                    "submit_instruction": "Final review and submission must remain manual.",
                },
            }
        ),
        encoding="utf-8",
    )


def test_autofill_context_prepares_tailored_resume_without_existing_packet(tmp_path) -> None:
    service = build_service(tmp_path)
    response = service.load_or_prepare(
        AutofillContextRequest(
            url="https://example.com/jobs/R123456/artificial-intelligence-engineer",
            page_title="Artificial Intelligence Engineer | Example Robotics",
            page_text="""
            Artificial Intelligence Engineer
            Example Robotics is hiring a junior Artificial Intelligence Engineer.
            Responsibilities include Python, machine learning, model evaluation, API development,
            data pipelines, Docker deployment, and cross functional analytics.
            Requirements: Python, SQL, scikit-learn, PyTorch, FastAPI, Docker.
            Preferred: RAG, LangChain, computer vision, AWS.
            Location: Remote, United States.
            """,
            output_root_override=str(tmp_path / "autofill_packets"),
            render_pdf=False,
        )
    )

    assert response.source == "prepared_tailored_resume"
    assert response.prepared_apply_plan_path.endswith("apply_plan.json")
    assert response.prepared_resume_path.endswith(".docx")
    assert response.prepared_resume_docx_path == response.prepared_resume_path
    assert response.prepared_resume_html_path.endswith(".html")
    assert response.prepared_resume_pdf_path == ""
    assert response.pdf_rendered is False
    assert response.intended_resume_pdf_path.endswith(".pdf")
    assert any(path.endswith(".docx") for path in response.files_written)
    assert any(path.endswith(".html") for path in response.files_written)
    assert response.apply_plan["job"]["company"] == "Example Robotics"
    assert response.apply_plan["job"]["role"] == "Artificial Intelligence Engineer"
    assert response.apply_plan["resume"]["tailored_resume_path"].endswith(".docx")
    assert response.apply_plan["resume"]["tailored_resume_docx_path"].endswith(".docx")
    assert response.apply_plan["ats_answer_bank"]["candidate"]["linkedin_url"].startswith("https://")


def test_force_prepare_saves_resume_to_configured_resume_root(tmp_path) -> None:
    resume_root = tmp_path / "configured_resumes"
    profile_path = tmp_path / "application_profile.json"
    write_profile(profile_path, resume_root)

    packet_dir = tmp_path / "autofill_packets" / "OldCo" / "application_packets" / "20260526_role"
    packet_dir.mkdir(parents=True)
    (packet_dir / "apply_plan.json").write_text(
        json.dumps(
            {
                "job": {
                    "job_id": "R123456",
                    "company": "OldCo",
                    "role": "Old Role",
                    "official_url": "https://example.com/jobs/R123456/artificial-intelligence-engineer",
                },
                "ats_answer_bank": {"candidate": {"email": "old@example.com"}},
            }
        ),
        encoding="utf-8",
    )

    response = build_service(tmp_path, profile_path=str(profile_path)).load_or_prepare(
        AutofillContextRequest(
            url="https://example.com/jobs/R123456/artificial-intelligence-engineer",
            page_title="Artificial Intelligence Engineer | Example Robotics",
            page_text="""
            Artificial Intelligence Engineer
            Example Robotics is hiring a junior Artificial Intelligence Engineer.
            Responsibilities include Python, machine learning, model evaluation, API development,
            data pipelines, Docker deployment, and cross functional analytics.
            Requirements: Python, SQL, scikit-learn, PyTorch, FastAPI, Docker.
            Preferred: RAG, LangChain, computer vision, AWS.
            Location: Remote, United States.
            """,
            company="Example Robotics",
            role="Artificial Intelligence Engineer",
            output_root_override="",
            force_prepare=True,
            render_pdf=False,
        )
    )

    assert response.source == "prepared_tailored_resume"
    assert str(resume_root) in response.prepared_resume_path
    assert Path(response.prepared_resume_path).exists()
    assert response.prepared_resume_docx_path == response.prepared_resume_path
    assert str(resume_root) in response.prepared_apply_plan_path
    assert response.apply_plan["job"]["company"] == "Example Robotics"


def test_autofill_context_prepares_tailored_resume_from_zoho_job_header(tmp_path) -> None:
    response = build_service(tmp_path).load_or_prepare(
        AutofillContextRequest(
            url="https://aspire.zohorecruit.com/jobs/Careers/503306000042101001",
            page_title="Aspire - Business Analyst - Remote Job",
            page_text="""
            Aspire | Full time Business Analyst Remote Job | Posted on 06/02/2026
            Job Description
            This team supports critical financial systems and is responsible for day-to-day
            operational support and strategic project work.
            Key responsibilities include managing billing support issues and financial
            system inquiries, owning triage so incidents and requests are routed to
            appropriate teams, performing root cause analysis, executing data fixes, and
            supporting incident and event management.
            Requirements: SQL, Excel, Power BI, analytics, stakeholder documentation,
            process analysis, reporting, and cross functional communication.
            Location: Remote Job.
            """,
            output_root_override=str(tmp_path / "autofill_packets"),
            force_prepare=True,
            render_pdf=False,
        )
    )

    assert response.source == "prepared_tailored_resume"
    assert response.apply_plan["job"]["company"] == "Aspire"
    assert response.apply_plan["job"]["role"] == "Business Analyst"
    assert response.apply_plan["decision"]["target_role_key"] == "business_analyst"
    assert response.prepared_resume_docx_path.endswith(".docx")


def test_force_prepare_fetches_jd_when_extension_page_text_is_empty(tmp_path, monkeypatch) -> None:
    service = build_service(tmp_path)
    monkeypatch.setattr(
        service,
        "_fetch_page_text",
        lambda _url: """
        Aspire | Full time Business Analyst Remote Job | Posted on 06/02/2026
        Job Description
        Responsibilities include financial systems analysis, billing support triage,
        incident routing, root cause analysis, analytics reporting, SQL, Excel,
        Power BI dashboards, stakeholder documentation, and cross functional communication.
        Requirements: SQL, Excel, Power BI, analytics, reporting, and process analysis.
        Location: Remote Job.
        """,
    )

    response = service.load_or_prepare(
        AutofillContextRequest(
            url="https://aspire.zohorecruit.com/jobs/Careers/503306000042101001",
            page_title="Aspire - Business Analyst - Remote Job",
            page_text="",
            output_root_override=str(tmp_path / "autofill_packets"),
            force_prepare=True,
            render_pdf=False,
        )
    )

    assert response.source == "prepared_tailored_resume"
    assert response.apply_plan["job"]["company"] == "Aspire"
    assert response.apply_plan["job"]["role"] == "Business Analyst"
    assert response.prepared_resume_path.endswith(".docx")


def test_autofill_context_uses_existing_matched_packet(tmp_path) -> None:
    packet_dir = tmp_path / "autofill_packets" / "ExistingCo" / "application_packets" / "20260526_role"
    packet_dir.mkdir(parents=True)
    apply_plan_path = packet_dir / "apply_plan.json"
    resume_path = packet_dir / "tailored_resume.html"
    resume_path.write_text("<html><body>resume</body></html>", encoding="utf-8")
    apply_plan_path.write_text(
        json.dumps(
            {
                "job": {
                    "job_id": "R99999",
                    "company": "ExistingCo",
                    "role": "Data Scientist",
                    "official_url": "https://example.com/jobs/R99999",
                },
                "resume": {
                    "tailored_resume_path": str(resume_path),
                    "tailored_resume_html_path": str(resume_path),
                    "tailored_resume_pdf_path": "",
                },
                "ats_answer_bank": {"candidate": {"email": "test@example.com"}},
            }
        ),
        encoding="utf-8",
    )

    response = build_service(tmp_path).load_or_prepare(
        AutofillContextRequest(
            url="https://example.com/apply/R99999",
            page_title="Data Scientist | ExistingCo",
            page_text="Data Scientist Python SQL machine learning",
            output_root_override=str(tmp_path / "autofill_packets"),
            render_pdf=False,
        )
    )

    assert response.source == "matched_apply_plan"
    assert response.matched_apply_plan_path == str(apply_plan_path)
    assert response.prepared_resume_path == str(resume_path)
    assert response.prepared_resume_html_path == str(resume_path)
    assert response.prepared_packet_folder_path == str(packet_dir)
    assert response.apply_plan["job"]["company"] == "ExistingCo"


def test_force_prepare_reuses_matched_packet_when_page_text_is_unavailable(tmp_path, monkeypatch) -> None:
    packet_dir = tmp_path / "autofill_packets" / "Aspire" / "application_packets" / "20260610_business_analyst"
    packet_dir.mkdir(parents=True)
    apply_plan_path = packet_dir / "apply_plan.json"
    resume_path = tmp_path / "autofill_packets" / "Aspire" / "Akhilesh_Kumbhar_Aspire_business_analyst.docx"
    resume_path.write_text("resume", encoding="utf-8")
    apply_plan_path.write_text(
        json.dumps(
            {
                "job": {
                    "job_id": "503306000042101001",
                    "company": "Aspire",
                    "role": "Business Analyst",
                    "official_url": "https://aspire.zohorecruit.com/jobs/Careers/503306000042101001",
                },
                "resume": {
                    "tailored_resume_path": str(resume_path),
                    "tailored_resume_docx_path": str(resume_path),
                },
                "ats_answer_bank": {"candidate": {"email": "test@example.com"}},
            }
        ),
        encoding="utf-8",
    )

    service = build_service(tmp_path)
    monkeypatch.setattr(service, "_fetch_page_text", lambda _url: "")
    response = service.load_or_prepare(
        AutofillContextRequest(
            url="https://aspire.zohorecruit.com/jobs/Careers/503306000042101001",
            page_title="Aspire - Business Analyst - Remote Job",
            page_text="",
            output_root_override=str(tmp_path / "autofill_packets"),
            force_prepare=True,
            render_pdf=False,
        )
    )

    assert response.source == "matched_apply_plan"
    assert response.prepared_resume_path == str(resume_path)
    assert "Using the existing matched tailored resume" in response.message
    assert "application form rather than the full job description" not in response.message


class _StubTailorer:
    """Always returns a tailored draft, isolating the force_prepare gate behavior from the
    rule-based scorer's own threshold."""

    def tailor(self, payload):
        from app.schemas.resume import ResumeTailorResponse

        return ResumeTailorResponse(
            job_id=payload.job_id,
            resume_version=payload.resume_version,
            source_resume_version=payload.resume_version,
            tailored_resume_version=f"{payload.job_id}_tailored_v1",
            tailored_score=82,
            selected_project_ids=[],
            changes_summary=["stub tailoring"],
            summary_variant_key="ml_engineer",
            summary_text="Stub tailored summary for an off-allowlist role.",
        )


class _PreferenceCaptureTailorer(_StubTailorer):
    def __init__(self) -> None:
        self.preferences = None

    def tailor(self, payload):
        self.preferences = payload.preferences
        return super().tailor(payload)


def test_force_prepare_passes_third_eye_tailoring_preferences(tmp_path) -> None:
    from app.schemas.resume import TailoringPreferences

    tailorer = _PreferenceCaptureTailorer()
    service = AutofillContextService(
        autofill=ATSAutofillService(apply_plan_roots=[str(tmp_path / "autofill_packets")]),
        parser=JDParserService(),
        scorer=ScoringService(),
        tailorer=tailorer,
        decider=DecisionService(),
        quality_gate=JobQualityGateService(),
        packet_builder=ApplicationPacketService(),
        packet_exporter=ApplicationPacketExportService(),
    )

    response = service.load_or_prepare(
        AutofillContextRequest(
            url="https://jobs.example.com/operations-data-analyst",
            page_title="Operations Data Analyst | Example",
            page_text="""
            Operations Data Analyst
            Responsibilities include collecting, analyzing, and visualizing operational data,
            preparing reports, improving business processes, and communicating recommendations.
            Requirements: Python, SQL, Tableau, reporting, analytics, and stakeholder communication.
            Location: Las Vegas, Nevada, United States.
            """,
            output_root_override=str(tmp_path / "autofill_packets"),
            force_prepare=True,
            render_pdf=False,
            tailoring_preferences=TailoringPreferences(
                preset="business_impact",
                rewrite_intensity="light",
                emphasis=["experience", "skills"],
                custom_instructions="Keep project wording close to the original.",
                include_connection_note=False,
            ),
        )
    )

    assert response.source == "prepared_tailored_resume"
    assert tailorer.preferences.preset == "business_impact"
    assert tailorer.preferences.rewrite_intensity == "light"
    assert tailorer.preferences.emphasis == ["experience", "skills"]
    assert tailorer.preferences.custom_instructions == "Keep project wording close to the original."
    assert tailorer.preferences.include_connection_note is False


def test_force_prepare_tailors_even_when_title_is_not_a_configured_role(tmp_path) -> None:
    # "No hardcoded gate": an explicit Tailor request must not be blocked just because the
    # title is not in the configured target-role allowlist. The tailorer infers the role.
    service = AutofillContextService(
        autofill=ATSAutofillService(apply_plan_roots=[str(tmp_path / "autofill_packets")]),
        parser=JDParserService(),
        scorer=ScoringService(),
        tailorer=_StubTailorer(),
        decider=DecisionService(),
        quality_gate=JobQualityGateService(),
        packet_builder=ApplicationPacketService(),
        packet_exporter=ApplicationPacketExportService(),
    )
    response = service.load_or_prepare(
        AutofillContextRequest(
            url="https://jobs.example.com/robotics-perception-developer",
            page_title="Robotics Perception Developer",
            page_text="""
            Robotics Perception Developer
            Build perception software for robots. Responsibilities include developing models in
            Python, processing sensor data, and deploying to edge devices. Requirements: Python,
            C++, SQL, and model deployment. Preferred: Docker. Up to 2 years of experience.
            Location: Remote, United States.
            """,
            output_root_override=str(tmp_path / "autofill_packets"),
            force_prepare=True,
            render_pdf=False,
        )
    )

    assert response.source == "prepared_tailored_resume"
    assert response.prepared_resume_path.endswith(".docx")


def test_autofill_context_does_not_call_form_page_quality_reject_tailoring(tmp_path) -> None:
    response = build_service(tmp_path).load_or_prepare(
        AutofillContextRequest(
            url="https://hdfc.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/4218/apply/section/1",
            page_title="Personal Info - Associate, Research Analytics",
            page_text="""
            Supporting Documents Please attach your resume. Drop Resume Here.
            Contact Information Legal First Name Legal Last Name Email Phone.
            Link 1 Add Another Link.
            """,
            output_root_override=str(tmp_path / "autofill_packets"),
            render_pdf=False,
        )
    )

    assert response.source == "profile_fallback"
    assert "application form rather than the full job description" in response.message
    assert "Quality gate rejected" not in response.message
