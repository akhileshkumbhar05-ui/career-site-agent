from datetime import UTC, datetime, timedelta

from app.services.web_job_search_service import WebJobSearchService


def test_search_jobs_ranks_across_feeds_instead_of_stopping_at_first_source(monkeypatch) -> None:
    service = WebJobSearchService()

    monkeypatch.setattr(
        service,
        "_search_public_job_feeds",
        lambda **_kwargs: [
            {
                "job_id": "public_low",
                "company": "SeniorCo",
                "title": "Senior Data Engineer",
                "jd_text": "Requires 6 years experience.",
                "discovered_url": "https://example.com/senior",
                "source": "Web Feed: Example",
                "location": "United States",
            },
            {
                "job_id": "public_good",
                "company": "FeedCo",
                "title": "Data Analyst Entry Level",
                "jd_text": "Python SQL analytics. Entry level.",
                "discovered_url": "https://example.com/analyst",
                "source": "Web Feed: Example",
                "location": "Remote in USA",
            },
        ],
    )
    monkeypatch.setattr(service, "_queries", lambda: ["junior data scientist"])
    monkeypatch.setattr(
        service,
        "_search_duckduckgo",
        lambda *_args, **_kwargs: [
            {
                "title": "Junior Data Scientist at SearchCo",
                "url": "https://searchco.example/jobs/junior-data-scientist",
                "snippet": "New grad Python SQL machine learning role in United States.",
                "query": "junior data scientist",
            }
        ],
    )
    monkeypatch.setattr(
        service,
        "_result_to_job",
        lambda result: {
            "job_id": "search_high",
            "company": "SearchCo",
            "title": "Junior Data Scientist",
            "jd_text": "New grad Python SQL machine learning role in United States.",
            "discovered_url": result["url"],
            "source": "Web Search: searchco.example",
            "location": "United States",
        },
    )

    jobs = service.search_jobs(max_results=2)

    assert [job["job_id"] for job in jobs] == ["search_high", "public_good"]
    assert all(job["discovery_score"] >= 50 for job in jobs)


def test_web_search_skips_blocked_jobright_urls_before_fetching(monkeypatch) -> None:
    service = WebJobSearchService()
    fetched_urls: list[str] = []

    monkeypatch.setattr(service, "_search_public_job_feeds", lambda **_kwargs: [])
    monkeypatch.setattr(service, "_queries", lambda: ["junior data scientist"])
    monkeypatch.setattr(
        service,
        "_search_duckduckgo",
        lambda *_args, **_kwargs: [
            {
                "title": "Junior Data Scientist at BlockedCo",
                "url": "https://jobright.ai/jobs/info/abc123",
                "snippet": "Python SQL machine learning role in United States.",
                "query": "junior data scientist",
            },
            {
                "title": "Junior Data Scientist at ExampleCo",
                "url": "https://example.com/jobs/junior-data-scientist",
                "snippet": "Python SQL machine learning role in United States.",
                "query": "junior data scientist",
            },
        ],
    )

    def fake_fetch(url: str) -> str:
        fetched_urls.append(url)
        return "Responsibilities include Python, SQL, machine learning, analytics, and model evaluation in the United States."

    monkeypatch.setattr(service, "_fetch_page_text", fake_fetch)

    jobs = service.search_jobs(max_results=2)

    assert fetched_urls == ["https://example.com/jobs/junior-data-scientist"]
    assert jobs[0]["company"] == "ExampleCo"


def test_search_jobs_uses_bing_fallback_when_duckduckgo_returns_empty(monkeypatch) -> None:
    service = WebJobSearchService()
    monkeypatch.setattr(service, "_search_public_job_feeds", lambda **_kwargs: [])
    monkeypatch.setattr(service, "_queries", lambda: ["junior data scientist"])
    monkeypatch.setattr(service, "_search_duckduckgo", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        service,
        "_search_bing",
        lambda *_args, **_kwargs: [
            {
                "title": "Junior Data Scientist at FallbackCo",
                "url": "https://fallback.example/jobs/junior-data-scientist",
                "snippet": "Python SQL machine learning role in the United States.",
                "query": "junior data scientist",
            }
        ],
    )
    monkeypatch.setattr(
        service,
        "_fetch_page_text",
        lambda _url: "Responsibilities include Python, SQL, analytics, and machine learning in the United States.",
    )

    jobs = service.search_jobs(max_results=2)

    assert len(jobs) == 1
    assert jobs[0]["company"] == "FallbackCo"


def test_simplify_new_grad_parser_keeps_entry_level_data_roles(monkeypatch) -> None:
    service = WebJobSearchService()
    readme = """
## Data Science, AI & Machine Learning New Grad Roles

<table>
<thead><tr><th>Company</th><th>Role</th><th>Location</th><th>Application</th><th>Age</th></tr></thead>
<tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/Murj">Murj</a></strong></td>
<td>Data Analyst Entry Level</td>
<td>Remote in USA</td>
<td><a href="https://job-boards.greenhouse.io/murj/jobs/5219884008">Apply</a></td>
<td>2d</td>
</tr>
<tr>
<td><strong><a href="https://simplify.jobs/c/SeniorCo">SeniorCo</a></strong></td>
<td>Senior Data Scientist</td>
<td>New York, NY</td>
<td><a href="https://example.com/senior">Apply</a></td>
<td>1d</td>
</tr>
<tr>
<td><strong><a href="https://simplify.jobs/c/ClearanceCo">ClearanceCo</a></strong></td>
<td>Software Engineer 1 - U.S. Citizenship Required</td>
<td>Seattle, WA</td>
<td><a href="https://example.com/clearance">Apply</a></td>
<td>1d</td>
</tr>
<tr>
<td><strong><a href="https://simplify.jobs/c/IntelCo">IntelCo</a></strong></td>
<td>Open Source Intelligence Analyst</td>
<td>Remote in USA</td>
<td><a href="https://example.com/intel">Apply</a></td>
<td>1d</td>
</tr>
<tr>
<td><strong><a href="https://simplify.jobs/c/BackendCo">BackendCo</a></strong></td>
<td>Software Engineer 1 - Backend</td>
<td>Remote in USA</td>
<td><a href="https://example.com/backend">Apply</a></td>
<td>1d</td>
</tr>
<tr>
<td><strong><a href="https://simplify.jobs/c/StaleCo">StaleCo</a></strong></td>
<td>Junior Data Scientist</td>
<td>Remote in USA</td>
<td><a href="https://example.com/stale">Apply</a></td>
<td>2mo</td>
</tr>
</tbody>
</table>
"""

    class FakeResponse:
        text = readme

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, *_args, **_kwargs) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("app.services.web_job_search_service.httpx.Client", FakeClient)

    jobs = service._search_simplify_new_grad(max_results=10)

    assert len(jobs) == 1
    assert jobs[0]["company"] == "Murj"
    assert jobs[0]["title"] == "Data Analyst Entry Level"
    assert jobs[0]["discovered_url"].endswith("/5219884008")


def test_remotejobs_org_parser_keeps_us_profile_roles(monkeypatch) -> None:
    service = WebJobSearchService()

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": [
                    {
                        "title": "Data Analyst",
                        "description": (
                            "<p>Responsibilities include SQL, Python, analytics, dashboards, "
                            "and machine learning for an entry level role in the United States.</p>"
                        ),
                        "location": "Remote, United States",
                        "company": {"name": "Remote Data Co"},
                        "apply_url": "https://remotejobs.org/jobs/data-analyst",
                        "posted_at": "2026-06-08T12:00:00Z",
                        "type": "Full-time",
                    },
                    {
                        "title": "Senior Data Scientist",
                        "description": "<p>Responsibilities include Python and machine learning.</p>",
                        "location": "Remote, United States",
                        "company": {"name": "Senior Co"},
                        "apply_url": "https://remotejobs.org/jobs/senior-data-scientist",
                    },
                    {
                        "title": "Data Analyst",
                        "description": "<p>Responsibilities include SQL, Python, and analytics.</p>",
                        "location": "Remote - Spain",
                        "company": {"name": "Spain Co"},
                        "apply_url": "https://remotejobs.org/jobs/spain-data-analyst",
                    },
                ],
                "pagination": {"has_more": False},
            }

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, *_args, **_kwargs) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("app.services.web_job_search_service.httpx.Client", FakeClient)

    jobs = service._search_remotejobs_org(max_results=5)

    assert len(jobs) == 1
    assert jobs[0]["company"] == "Remote Data Co"
    assert jobs[0]["title"] == "Data Analyst"
    assert jobs[0]["source"] == "Web Feed: RemoteJobs.org"


def test_location_ok_requires_us_scope_for_remote_only_jobs() -> None:
    service = WebJobSearchService()

    assert service._location_ok("Remote", "This role is open in the United States for Python analytics work.")
    assert not service._location_ok("Remote", "This role is open in Europe for Python analytics work.")


def test_posted_age_parser_handles_relative_iso_and_timestamps() -> None:
    service = WebJobSearchService()
    now = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)

    assert service.posted_age_hours("2h ago", now=now) == 2
    assert service.posted_age_hours("45 minutes ago", now=now) == 0.75
    assert service.posted_age_hours("1mo", now=now) == 24 * 30
    assert service.posted_age_hours("1 year", now=now) == 24 * 365
    assert service.posted_age_hours((now - timedelta(hours=23)).isoformat(), now=now) == 23
    assert service.posted_age_hours((now - timedelta(hours=25)).timestamp(), now=now) == 25
    assert service.posted_age_hours("not a date", now=now) is None


def test_posted_age_parser_handles_public_month_day_dates() -> None:
    service = WebJobSearchService()
    now = datetime(2026, 6, 5, 20, 0, tzinfo=UTC)

    assert service.posted_age_hours("Jun 05", now=now) == 20
    assert service.posted_age_hours("Jun 04", now=now) == 44


def test_search_recent_jobs_filters_to_parseable_last_24h_profile_jobs(monkeypatch) -> None:
    service = WebJobSearchService()
    now = datetime.now(UTC)
    monkeypatch.setattr(
        service,
        "_search_public_job_feeds",
        lambda **_kwargs: [
            {
                "job_id": "fresh_good",
                "company": "FreshCo",
                "title": "Junior Data Scientist",
                "jd_text": "Python SQL machine learning. Entry level role in United States.",
                "discovered_url": "https://example.com/fresh",
                "source": "Web Feed: Example",
                "location": "Remote, United States",
                "posted_at": (now - timedelta(hours=3)).isoformat(),
            },
            {
                "job_id": "stale_good",
                "company": "StaleCo",
                "title": "Junior Data Scientist",
                "jd_text": "Python SQL machine learning. Entry level role in United States.",
                "discovered_url": "https://example.com/stale",
                "source": "Web Feed: Example",
                "location": "Remote, United States",
                "posted_at": (now - timedelta(hours=30)).isoformat(),
            },
            {
                "job_id": "unknown_age",
                "company": "UnknownCo",
                "title": "Junior Data Scientist",
                "jd_text": "Python SQL machine learning. Entry level role in United States.",
                "discovered_url": "https://example.com/unknown",
                "source": "Web Feed: Example",
                "location": "Remote, United States",
            },
        ],
    )

    jobs = service.search_recent_jobs(max_results=10, hours=24)

    assert [job["job_id"] for job in jobs] == ["fresh_good"]
    assert jobs[0]["freshness_hours"] <= 24
    assert jobs[0]["source_scope"] == "fresh_24h"


def test_sponsored_entry_jobs_require_explicit_early_career_signal(monkeypatch) -> None:
    service = WebJobSearchService()
    sponsors = [
        {
            "employer_name": "Sponsor AI Inc.",
            "certified_lca_count": 12,
            "relevant_lca_count": 8,
            "entry_level_lca_count": 4,
            "source_url": "https://www.dol.gov/media/LCA_Dislclosure_Data_FY2026_Q2.xlsx",
            "fiscal_year": 2026,
            "quarter": 2,
        }
    ]

    monkeypatch.setattr(service, "_search_duckduckgo", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        service,
        "_search_bing",
        lambda *_args, **_kwargs: [
            {
                "title": "Data Scientist at Sponsor AI Inc.",
                "url": "https://sponsor.example/careers/data-scientist",
                "snippet": "Build Python machine learning models.",
                "query": "sponsor",
            },
            {
                "title": "Junior Data Analyst at Sponsor AI Inc.",
                "url": "https://sponsor.example/careers/junior-data-analyst",
                "snippet": "Entry level analytics role.",
                "query": "sponsor",
            },
        ],
    )

    def fake_fetch(url: str) -> str:
        if "junior" in url:
            return "Responsibilities include SQL, Python, dashboards, and machine learning. Entry level role, 0-2 years of experience."
        return "Responsibilities include Python, SQL, machine learning, analytics, and 5 years of experience."

    monkeypatch.setattr(service, "_fetch_page_text", fake_fetch)

    jobs = service.search_sponsored_entry_jobs(sponsors, max_results=5)

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Junior Data Analyst"
    assert jobs[0]["company"] == "Sponsor AI Inc."
    assert jobs[0]["is_h1b_sponsor"] is True
    assert jobs[0]["source_scope"] == "sponsor_backed_entry_search"


def test_result_to_job_rejects_listing_pages(monkeypatch) -> None:
    service = WebJobSearchService()
    monkeypatch.setattr(
        service,
        "_fetch_page_text",
        lambda _url: "38 Remote Junior Data Scientist Jobs in the United States. Browse jobs and apply to open roles.",
    )

    job = service._result_to_job(
        {
            "title": "38 Remote Junior Data Scientist Jobs in the United States",
            "url": "https://www.remoterocketship.com/country/united-states/jobs/junior-data-scientist",
            "snippet": "Browse remote junior data scientist jobs.",
            "query": "junior data scientist",
        }
    )

    assert job is None


def test_discovery_score_uses_structured_source_blockers() -> None:
    service = WebJobSearchService()

    good = service._with_discovery_score(
        {
            "title": "Junior Data Scientist",
            "company": "GoodCo",
            "jd_text": "Python SQL machine learning.",
            "location": "United States",
            "source": "Web Feed: Example",
            "job_seniority": "Entry Level",
            "is_h1b_sponsor": True,
        }
    )
    blocked = service._with_discovery_score(
        {
            "title": "Junior Data Scientist",
            "company": "BlockedCo",
            "jd_text": "Python SQL machine learning.",
            "location": "United States",
            "source": "Web Feed: Example",
            "job_seniority": "Entry Level",
            "is_clearance_required": True,
        }
    )

    assert good["discovery_score"] >= 80
    assert blocked["discovery_score"] < 50
