from types import SimpleNamespace

from app.services.job_visibility_service import JobVisibilityService


def test_job_visibility_hides_jobs_by_normalized_url(tmp_path) -> None:
    service = JobVisibilityService(state_path=str(tmp_path / "job_visibility.json"))
    job = {
        "company": "GumGum",
        "title": "Data Scientist",
        "discovered_url": "https://jobs.example.com/posting/123/?b=2&a=1#apply",
    }

    service.mark_hidden(job, reason="already_applied")

    same_job = {
        "company": "GumGum",
        "title": "Data Scientist",
        "official_url": "https://jobs.example.com/posting/123?a=1&b=2",
    }
    assert service.is_hidden(same_job)
    assert service.hidden_reason(same_job) == "already_applied"


def test_job_visibility_matches_applied_tracker_rows_by_title_and_company(tmp_path) -> None:
    service = JobVisibilityService(state_path=str(tmp_path / "job_visibility.json"))
    job = {
        "company": "GumGum",
        "title": "Data Scientist",
        "location": "Santa Monica, California, United States",
    }
    row = SimpleNamespace(
        company_applied="GumGum",
        role="Data Scientist | Santa Monica, California, United States",
        link="",
    )

    assert service.is_applied_in_tracker(job, [row])


def test_job_visibility_resolves_agent_packet_urls_before_fallbacks(tmp_path) -> None:
    service = JobVisibilityService(state_path=str(tmp_path / "job_visibility.json"))

    assert (
        service.resolve_url(
            {
                "discovered_url": "",
                "official_url": "https://careers.example.com/jobs/42",
                "url": "https://fallback.example.com/jobs/42",
            }
        )
        == "https://careers.example.com/jobs/42"
    )


def test_job_visibility_lists_applied_jobs_with_snapshot(tmp_path) -> None:
    service = JobVisibilityService(state_path=str(tmp_path / "job_visibility.json"))
    job = {
        "company": "GumGum",
        "title": "Data Scientist",
        "jd_text": "Python, SQL, and machine learning.",
        "discovered_url": "https://jobs.example.com/posting/123",
    }

    record = service.mark_applied(job)
    applied = service.applied_jobs()

    assert record["reason"] == "already_applied"
    assert len(applied) == 1
    assert applied[0]["job"]["company"] == "GumGum"
    assert applied[0]["job"]["jd_text"] == "Python, SQL, and machine learning."
    assert service.list_hidden(reason="dismissed") == []
