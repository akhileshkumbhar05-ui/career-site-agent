from app.schemas.job import ParsedJD
from app.schemas.resume import ResumeTailorRequest, TailoringPreferences
from app.services.claude_tailoring_service import ClaudeTailoringService
from app.services.tailoring_service import TailoringService


def test_tailoring_increases_score():
    service = TailoringService()
    payload = ResumeTailorRequest(
        job_id='job2',
        parsed_jd=ParsedJD(
            job_id='job2',
            company='Example',
            title='Machine Learning Engineer',
            required_skills=['python', 'aws', 'deployment'],
            preferred_skills=['fastapi'],
            years_required='1+ years',
            education="master's",
            responsibilities=['Deploy ML systems'],
            keywords=['deployment', 'evaluation'],
            constraints=[]
        ),
        current_score=74
    )
    result = service.tailor(payload)
    assert result.tailored_score > payload.current_score


def test_tailoring_sets_role_specific_summary_text():
    service = TailoringService()
    payload = ResumeTailorRequest(
        job_id="job_business",
        parsed_jd=ParsedJD(
            job_id="job_business",
            company="Example",
            title="Business Analyst",
            required_skills=["sql", "excel", "power bi"],
            preferred_skills=["process analysis", "documentation"],
            years_required="0-2 years",
            education="bachelor's",
            responsibilities=["Analyze billing operations and document process improvements"],
            keywords=["analytics", "reporting", "stakeholder documentation"],
            constraints=[],
        ),
        current_score=78,
    )

    result = service.tailor(payload)

    assert result.summary_variant_key == "business_analyst"
    assert result.summary_text
    assert "Business Analyst" in result.summary_text
    assert "computer vision" not in result.summary_text.lower()
    assert "rag" not in result.summary_text.lower()


def test_tailoring_skips_low_score_roles():
    service = TailoringService()
    payload = ResumeTailorRequest(
        job_id="job_low",
        parsed_jd=ParsedJD(
            job_id="job_low",
            company="Example",
            title="Business Analyst",
            required_skills=["sap", "accounting", "billing operations"],
            preferred_skills=["finance domain"],
            years_required="5 years",
            education="bachelor's",
            responsibilities=["Own finance systems support"],
            keywords=["erp", "accounting"],
            constraints=[],
        ),
        current_score=52,
    )

    result = service.tailor(payload)

    assert result.tailored_score == 52
    assert result.selected_project_ids == []
    assert result.summary_text == ""
    assert "below the tailoring threshold" in result.changes_summary[0]


def test_rule_based_tailoring_honors_summary_and_project_emphasis():
    result = TailoringService().tailor(
        ResumeTailorRequest(
            job_id="job_preferences",
            parsed_jd=ParsedJD(
                job_id="job_preferences",
                company="Example",
                title="Data Analyst",
                required_skills=["python", "sql"],
                preferred_skills=["tableau"],
                responsibilities=["Analyze operational data"],
                keywords=["reporting", "analytics"],
                constraints=[],
            ),
            current_score=76,
            preferences=TailoringPreferences(
                preset="minimal_edits",
                rewrite_intensity="light",
                emphasis=["experience", "skills"],
            ),
        )
    )

    assert result.summary_text == ""
    assert result.selected_project_ids == []
    assert "minimal_edits with light edits" in result.changes_summary[0]


def test_claude_preference_text_keeps_custom_direction_explicit_and_bounded():
    text = ClaudeTailoringService._format_preferences(
        TailoringPreferences(
            preset="technical_depth",
            rewrite_intensity="strong",
            emphasis=["summary", "experience", "skills"],
            custom_instructions="Keep SAS visible only where the evidence supports it.",
            include_connection_note=False,
        )
    )

    assert "technical implementation details" in text
    assert "without exaggeration" in text
    assert "Do not generate" in text
    assert "Keep SAS visible only where the evidence supports it." in text


def test_claude_preferences_deterministically_remove_disabled_sections():
    adjusted = ClaudeTailoringService._apply_preferences(
        {
            "summary_text": "Tailored summary",
            "ranked_project_ids": ["project_one"],
            "rewritten_bullets": [
                {"section": "project", "rewritten": "Project rewrite"},
                {"section": "experience", "rewritten": "Experience rewrite"},
                {"section": "publication", "rewritten": "Research rewrite"},
            ],
            "connection_note": "Hello recruiter",
        },
        TailoringPreferences(
            emphasis=["experience", "skills"],
            include_connection_note=False,
        ),
    )

    assert adjusted["summary_text"] == ""
    assert adjusted["ranked_project_ids"] == []
    assert adjusted["rewritten_bullets"] == [
        {"section": "experience", "rewritten": "Experience rewrite"}
    ]
    assert adjusted["connection_note"] == ""


def test_claude_preference_filter_allows_research_paper_bullets():
    adjusted = ClaudeTailoringService._apply_preferences(
        {
            "summary_text": "Tailored summary",
            "ranked_project_ids": ["project_one"],
            "rewritten_bullets": [
                {"section": "publication", "rewritten": "Research rewrite"},
                {"section": "project", "rewritten": "Project rewrite"},
            ],
        },
        TailoringPreferences(
            emphasis=["summary", "research_papers"],
        ),
    )

    assert adjusted["ranked_project_ids"] == []
    assert adjusted["rewritten_bullets"] == [
        {"section": "publication", "rewritten": "Research rewrite"}
    ]


def test_claude_filter_removes_weak_rewrites():
    filtered = ClaudeTailoringService._filter_weak_rewrites(
        [
            {"section": "experience", "rewritten": "Responsible for analytics and reporting."},
            {
                "section": "experience",
                "rewritten": (
                    "Improved operational reporting visibility, as evidenced by Power BI dashboards, "
                    "by delivering reporting workflows over a three-tier service data model."
                ),
            },
        ]
    )

    assert filtered == [
        {
            "section": "experience",
            "rewritten": (
                "Improved operational reporting visibility, as evidenced by Power BI dashboards, "
                "by delivering reporting workflows over a three-tier service data model."
            ),
        }
    ]
