from app.services.h1b_sponsor_service import H1BSponsorService


def test_sponsors_from_lca_rows_keeps_relevant_certified_h1b_entry_level_rows() -> None:
    rows = [
        {
            "EMPLOYER_NAME": "Good AI Inc.",
            "CASE_STATUS": "Certified",
            "VISA_CLASS": "H-1B",
            "JOB_TITLE": "Data Scientist",
            "SOC_TITLE": "Data Scientists",
            "PW_WAGE_LEVEL": "Level I",
        },
        {
            "EMPLOYER_NAME": "Good AI Inc.",
            "CASE_STATUS": "Certified",
            "VISA_CLASS": "H-1B",
            "JOB_TITLE": "Machine Learning Engineer",
            "SOC_TITLE": "Software Developers",
            "PW_WAGE_LEVEL": "Level II",
        },
        {
            "EMPLOYER_NAME": "DeniedCo",
            "CASE_STATUS": "Denied",
            "VISA_CLASS": "H-1B",
            "JOB_TITLE": "Data Scientist",
            "SOC_TITLE": "Data Scientists",
            "PW_WAGE_LEVEL": "Level I",
        },
        {
            "EMPLOYER_NAME": "IrrelevantCo",
            "CASE_STATUS": "Certified",
            "VISA_CLASS": "H-1B",
            "JOB_TITLE": "Account Executive",
            "SOC_TITLE": "Sales Representatives",
            "PW_WAGE_LEVEL": "Level I",
        },
    ]

    sponsors = H1BSponsorService.sponsors_from_lca_rows(
        rows,
        source_url="https://www.dol.gov/media/LCA_Dislclosure_Data_FY2026_Q2.xlsx",
        fiscal_year=2026,
        quarter=2,
    )

    assert len(sponsors) == 1
    assert sponsors[0]["employer_name"] == "Good AI Inc."
    assert sponsors[0]["relevant_lca_count"] == 2
    assert sponsors[0]["entry_level_lca_count"] == 2
    assert sponsors[0]["is_h1b_sponsor"] is True
