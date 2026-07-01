from app.services.job_quality_gate_service import JobQualityGateService
from scripts.scrape_and_send_jobs import apply_quality_gate, write_scrape_report


def test_scrape_quality_gate_accepts_target_jobs_and_rejects_blockers():
    quality_gate = JobQualityGateService()
    jobs = [
        {
            "job_id": "junior_ds",
            "company": "Good Data Co",
            "title": "Junior Data Scientist",
            "jd_text": "Python, SQL, machine learning, dashboards. 1 year experience. No clearance requirement.",
            "discovered_url": "https://example.com/junior-ds",
            "source": "pytest",
            "location": "Remote, United States",
        },
        {
            "job_id": "senior_clearance",
            "company": "Blocked Co",
            "title": "Senior Data Scientist",
            "jd_text": "Requires active Secret clearance and US citizenship.",
            "discovered_url": "https://example.com/senior-clearance",
            "source": "pytest",
            "location": "United States",
        },
    ]

    accepted, report_rows = apply_quality_gate(jobs, quality_gate)

    assert [job["job_id"] for job in accepted] == ["junior_ds"]
    assert len(report_rows) == 2
    assert report_rows[0]["quality_decision"] in {"pass", "review"}
    assert report_rows[1]["quality_decision"] == "reject"
    assert report_rows[1]["blockers"]


def test_scrape_report_includes_target_diagnostics(tmp_path):
    report_path = write_scrape_report(
        report_rows=[],
        summary={"dry_run": True, "total_scraped": 0},
        target_rows=[
            {
                "company": "Stale Board",
                "ats_type": "greenhouse",
                "url": "https://example.com/jobs",
                "status": "failed",
                "error": "404 Not Found",
            }
        ],
        report_dir=tmp_path,
    )

    text = report_path.read_text(encoding="utf-8")
    assert "Stale Board" in text
    assert "404 Not Found" in text
