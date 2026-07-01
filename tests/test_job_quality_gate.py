from app.schemas.job import JobQualityGateRequest
from app.services.job_quality_gate_service import JobQualityGateService


def test_quality_gate_accepts_junior_data_science_role():
    service = JobQualityGateService()

    result = service.evaluate(
        JobQualityGateRequest(
            company="Example",
            title="Junior Data Scientist",
            jd_text="Build machine learning models with Python and SQL. 0-1 years experience preferred.",
            location="United States",
        )
    )

    assert result.decision == "pass"
    assert result.actionable is True
    assert result.role_key == "data_scientist"


def test_quality_gate_accepts_entry_level_data_engineering_as_adjacent_target():
    service = JobQualityGateService()

    result = service.evaluate(
        JobQualityGateRequest(
            company="Example",
            title="Data Analytics Engineer 1",
            jd_text="Build SQL and Python analytics pipelines. 1 year experience preferred.",
            location="United States",
        )
    )

    assert result.decision == "pass"
    assert result.actionable is True
    assert result.role_key == "data_engineer"


def test_quality_gate_rejects_non_us_location_when_profile_is_us_only():
    service = JobQualityGateService()

    result = service.evaluate(
        JobQualityGateRequest(
            company="Example",
            title="AI Engineer",
            jd_text="Build LLM applications with Python and SQL. 0-1 years experience preferred.",
            location="Remote - Spain",
        )
    )

    assert result.decision == "reject"
    assert any("united states search scope" in blocker.lower() for blocker in result.blockers)


def test_quality_gate_routes_unclear_location_to_review():
    service = JobQualityGateService()

    result = service.evaluate(
        JobQualityGateRequest(
            company="Example",
            title="Data Analyst",
            jd_text="Build dashboards with Python and SQL. 0-1 years experience preferred.",
            location="North America",
        )
    )

    assert result.decision == "review"
    assert any("not clearly within" in reason.lower() for reason in result.reasons)


def test_quality_gate_rejects_security_clearance_role():
    service = JobQualityGateService()

    result = service.evaluate(
        JobQualityGateRequest(
            company="Defense Example",
            title="Machine Learning Engineer",
            jd_text="Applicants must be a U.S. citizen and maintain an active Secret clearance.",
            location="United States",
        )
    )

    assert result.decision == "reject"
    assert result.authorization_risk == "high"
    assert any("citizen" in blocker.lower() or "clearance" in blocker.lower() for blocker in result.blockers)


def test_quality_gate_rejects_no_h1b_tn_or_stem_opt_support():
    service = JobQualityGateService()

    result = service.evaluate(
        JobQualityGateRequest(
            company="Travelers",
            title="Data Engineer I",
            jd_text=(
                "Applicants must be authorized to work for ANY employer in the U.S. "
                "The company does not sponsor/support H-1B petitions, TN, or Forms I-983/STEM OPT, for this role."
            ),
            location="Atlanta, GA",
        )
    )

    assert result.decision == "reject"
    assert result.authorization_risk == "high"
    assert any("does not sponsor/support" in blocker.lower() for blocker in result.blockers)


def test_quality_gate_rejects_unable_to_support_visa_sponsorships():
    service = JobQualityGateService()

    result = service.evaluate(
        JobQualityGateRequest(
            company="Example",
            title="Data Analyst",
            jd_text="Note: we are unable to support visa sponsorships at this time.",
            location="United States",
        )
    )

    assert result.decision == "reject"
    assert result.authorization_risk == "high"


def test_quality_gate_rejects_no_opt_cpt_stem_or_future_sponsorship():
    service = JobQualityGateService()

    result = service.evaluate(
        JobQualityGateRequest(
            company="Cox",
            title="Entry Level Data Engineer",
            jd_text=(
                "Applicants must currently be authorized to work in the United States for any employer "
                "without current or future sponsorship. No OPT, CPT, STEM/OPT or visa sponsorship now or in future."
            ),
            location="Atlanta, GA",
            source="Web Feed: Simplify New Grad",
        )
    )

    assert result.decision == "reject"
    assert result.actionable is False
    assert result.authorization_risk == "high"
    assert any("sponsor" in blocker.lower() for blocker in result.blockers)


def test_quality_gate_rejects_senior_or_high_experience_role():
    service = JobQualityGateService()

    result = service.evaluate(
        JobQualityGateRequest(
            company="Example",
            title="Senior Data Scientist",
            jd_text="Requires 5+ years of machine learning experience.",
            location="United States",
        )
    )

    assert result.decision == "reject"
    assert result.experience_risk == "high"


def test_quality_gate_rejects_two_plus_years_required_for_junior_target():
    service = JobQualityGateService()

    result = service.evaluate(
        JobQualityGateRequest(
            company="Example",
            title="Data Engineer I",
            jd_text="Basic Qualifications: 2+ years of data engineering experience. Experience building ETL pipelines.",
            location="United States",
        )
    )

    assert result.decision == "reject"
    assert result.experience_risk == "high"
    assert result.years_required == 2


def test_quality_gate_ignores_company_history_years():
    service = JobQualityGateService()

    result = service.evaluate(
        JobQualityGateRequest(
            company="Travelers",
            title="Data Engineer I",
            jd_text=(
                "We have maintained our reputation as one of the best insurers in the industry for over 170 years. "
                "Build data pipelines and analytics products with Python and SQL."
            ),
            location="Atlanta, GA",
        )
    )

    assert result.decision == "pass"
    assert result.years_required is None


def test_quality_gate_routes_sponsorship_ambiguity_to_review():
    service = JobQualityGateService()

    result = service.evaluate(
        JobQualityGateRequest(
            company="Example",
            title="AI Engineer",
            jd_text="Candidates must have employment authorization. Sponsorship may be discussed.",
            location="United States",
        )
    )

    assert result.decision == "review"
    assert result.authorization_risk == "medium"


def test_quality_gate_rejects_language_specific_roles_not_in_profile():
    service = JobQualityGateService()

    result = service.evaluate(
        JobQualityGateRequest(
            company="TELUS Digital",
            title="Online Data Analyst United States Spanish speakers",
            jd_text="Analyze online map data. Spanish speakers required for this role.",
            location="United States",
        )
    )

    assert result.decision == "reject"
    assert any("language requirement" in blocker.lower() for blocker in result.blockers)
