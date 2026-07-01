from datetime import UTC, datetime, timedelta

from app.services.job_feed_service import JobFeedService
from app.services.job_quality_gate_service import JobQualityGateService


def test_extract_text_uses_meta_description_for_javascript_ats_shell() -> None:
    html = """
    <html>
      <head>
        <title>Data Scientist, New Grad @ ExampleCo</title>
        <meta name="description" content="ExampleCo is hiring a Data Scientist. Responsibilities include Python, SQL, machine learning, model evaluation, data pipelines, and API development. Qualifications include a Bachelor's degree, analytics experience, and strong communication." />
      </head>
      <body>You need to enable JavaScript to run this app.</body>
    </html>
    """

    text = JobFeedService._extract_text(html)

    assert "Responsibilities include Python" in text
    assert "You need to enable JavaScript" not in text


def test_refresh_live_jobs_preserves_all_scraped_rows_for_review(tmp_path, monkeypatch) -> None:
    targets_path = tmp_path / "targets.json"
    cache_path = tmp_path / "latest_jobs.json"
    targets_path.write_text(
        """
        [
          {"company": "TargetCo", "ats_type": "greenhouse", "url": "https://example.com/targetco"}
        ]
        """,
        encoding="utf-8",
    )
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(targets_path),
        cache_path=str(cache_path),
    )

    monkeypatch.setattr(
        service,
        "_scrape_target",
        lambda *_args, **_kwargs: [
            {
                "job_id": "junior_ds",
                "company": "TargetCo",
                "title": "Junior Data Scientist",
                "jd_text": "Python SQL machine learning. 1 year experience.",
                "discovered_url": "https://example.com/targetco/junior-ds",
                "source": "pytest",
                "location": "Remote, United States",
            },
            {
                "job_id": "senior_clearance",
                "company": "TargetCo",
                "title": "Senior Security Engineer",
                "jd_text": "Requires active security clearance and 8 years of experience.",
                "discovered_url": "https://example.com/targetco/senior-security",
                "source": "pytest",
                "location": "United States",
            },
        ],
    )

    payload = service.refresh_live_jobs(max_companies=1, max_jobs_per_company=2, include_rejected=False)

    assert payload["targets"][0]["scraped"] == 2
    assert len(payload["all_jobs"]) == 2
    assert len(payload["jobs"]) == 1
    assert service.load_cached_scraped_jobs(limit=10)[1]["discovered_url"].endswith("senior-security")


def test_persist_payload_updates_cached_jobs(tmp_path) -> None:
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(tmp_path / "targets.json"),
        cache_path=str(tmp_path / "latest_jobs.json"),
    )
    payload = {
        "jobs": [{"job_id": "recommended", "title": "Junior Data Scientist"}],
        "all_jobs": [{"job_id": "recommended"}, {"job_id": "reviewed"}],
    }

    service.persist_payload(payload)

    assert service.load_cached_jobs(limit=10)[0]["job_id"] == "recommended"
    assert [job["job_id"] for job in service.load_cached_scraped_jobs(limit=10)] == ["recommended", "reviewed"]


def test_structured_board_scrapes_deeper_than_requested_card_count(tmp_path) -> None:
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(tmp_path / "targets.json"),
        cache_path=str(tmp_path / "latest_jobs.json"),
    )
    captured: dict[str, int] = {}

    class FakeGreenhouse:
        def scrape_jobs(self, **kwargs):
            captured["greenhouse"] = kwargs["max_jobs"]
            return []

    class FakeAshby:
        def scrape_jobs(self, **kwargs):
            captured["ashby"] = kwargs["max_jobs"]
            return []

    service.greenhouse = FakeGreenhouse()
    service.ashby = FakeAshby()

    service._scrape_target(
        {"company": "BigBoard", "ats_type": "greenhouse", "url": "https://job-boards.greenhouse.io/bigboard"},
        max_jobs=25,
    )
    service._scrape_target(
        {"company": "AshbyBoard", "ats_type": "ashby", "url": "https://jobs.ashbyhq.com/ashbyboard"},
        max_jobs=25,
    )

    assert captured == {"greenhouse": 150, "ashby": 150}


def test_cached_jobs_ignore_inactive_jobright_sources(tmp_path) -> None:
    cache_path = tmp_path / "latest_jobs.json"
    cache_path.write_text(
        """
        {
          "jobs": [
            {
              "job_id": "inactive",
              "company": "InactiveCo",
              "title": "Junior Data Scientist",
              "discovered_url": "https://jobright.ai/jobs/info/inactive",
              "source": "Public Curated Feed: Jobright"
            },
            {
              "job_id": "active",
              "company": "ActiveCo",
              "title": "Junior Data Scientist",
              "discovered_url": "https://example.com/active",
              "source": "Web Feed: Example"
            }
          ],
          "all_jobs": [
            {
              "job_id": "inactive_all",
              "company": "InactiveCo",
              "title": "Junior Data Scientist",
              "discovered_url": "https://jobright.ai/jobs/info/inactive-all",
              "source": "Public Curated Feed: Jobright"
            },
            {
              "job_id": "active_all",
              "company": "ActiveCo",
              "title": "Junior Data Scientist",
              "discovered_url": "https://example.com/active-all",
              "source": "Web Feed: Example"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(tmp_path / "targets.json"),
        cache_path=str(cache_path),
    )

    assert [job["job_id"] for job in service.load_cached_jobs(limit=10)] == ["active"]
    assert [job["job_id"] for job in service.load_cached_scraped_jobs(limit=10)] == ["active_all"]


def test_refresh_live_jobs_can_include_broad_web_sources(tmp_path, monkeypatch) -> None:
    targets_path = tmp_path / "targets.json"
    cache_path = tmp_path / "latest_jobs.json"
    targets_path.write_text("[]", encoding="utf-8")
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(targets_path),
        cache_path=str(cache_path),
    )
    monkeypatch.setattr(
        service.web,
        "search_jobs",
        lambda **_kwargs: [
            {
                "job_id": "web_ds",
                "company": "Open Web Co",
                "title": "Junior Data Scientist",
                "jd_text": "Python SQL machine learning. 1 year experience.",
                "discovered_url": "https://example.com/jobs/web-ds",
                "source": "Web Search: example.com",
                "location": "Remote, United States",
            }
        ],
    )

    payload = service.refresh_live_jobs(include_web=True, include_rejected=False, web_max_results=5)

    assert payload["targets"][0]["ats_type"] == "web"
    assert payload["targets"][0]["scraped"] == 1
    assert payload["jobs"][0]["source"] == "Web Search: example.com"


def test_refresh_live_jobs_can_include_dol_sponsor_backed_sources(tmp_path, monkeypatch) -> None:
    targets_path = tmp_path / "targets.json"
    cache_path = tmp_path / "latest_jobs.json"
    targets_path.write_text("[]", encoding="utf-8")
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(targets_path),
        cache_path=str(cache_path),
    )
    monkeypatch.setattr(service.web, "search_jobs", lambda **_kwargs: [])
    monkeypatch.setattr(
        service.h1b_sponsors,
        "load_sponsors",
        lambda **_kwargs: [
            {
                "employer_name": "Sponsor AI Inc.",
                "relevant_lca_count": 10,
                "entry_level_lca_count": 3,
                "is_h1b_sponsor": True,
            }
        ],
    )
    monkeypatch.setattr(
        service.web,
        "search_sponsored_entry_jobs",
        lambda *_args, **_kwargs: [
            {
                "job_id": "sponsor_ds",
                "company": "Sponsor AI Inc.",
                "title": "Junior Data Scientist",
                "jd_text": "Build Python SQL machine learning models. Entry level role, 0-2 years of experience.",
                "discovered_url": "https://example.com/sponsor-ds",
                "source": "Sponsor-backed Web Search: DOL OFLC LCA",
                "location": "United States",
                "is_h1b_sponsor": True,
                "h1b_relevant_lca_count": 10,
                "h1b_entry_level_lca_count": 3,
            }
        ],
    )

    payload = service.refresh_live_jobs(
        include_web=True,
        include_sponsors=True,
        include_rejected=False,
        web_max_results=5,
        sponsor_max_companies=5,
        sponsor_max_results=5,
    )

    assert payload["targets"][1]["ats_type"] == "sponsor_web"
    assert payload["targets"][1]["sponsor_count"] == 1
    assert payload["targets"][1]["kept"] == 1
    assert payload["jobs"][0]["job_id"] == "sponsor_ds"
    assert any("H1B sponsor signal" in signal for signal in payload["jobs"][0]["quality_signals"])


def test_refresh_live_jobs_tags_regular_results_with_dol_sponsor_signal(tmp_path, monkeypatch) -> None:
    targets_path = tmp_path / "targets.json"
    cache_path = tmp_path / "latest_jobs.json"
    targets_path.write_text("[]", encoding="utf-8")
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(targets_path),
        cache_path=str(cache_path),
    )
    monkeypatch.setattr(
        service.h1b_sponsors,
        "load_sponsors",
        lambda **_kwargs: [
            {
                "employer_name": "Google LLC",
                "certified_lca_count": 50,
                "relevant_lca_count": 20,
                "entry_level_lca_count": 5,
                "source_url": "https://www.dol.gov/media/LCA_Dislclosure_Data_FY2026_Q2.xlsx",
                "fiscal_year": 2026,
                "quarter": 2,
            }
        ],
    )
    monkeypatch.setattr(
        service.web,
        "search_jobs",
        lambda **_kwargs: [
            {
                "job_id": "google_da",
                "company": "Google",
                "title": "Junior Data Analyst",
                "jd_text": "Build SQL Python analytics dashboards. Entry level role, 0-2 years of experience.",
                "discovered_url": "https://example.com/google-da",
                "source": "Web Feed: Example",
                "location": "United States",
            }
        ],
    )
    monkeypatch.setattr(service.web, "search_sponsored_entry_jobs", lambda *_args, **_kwargs: [])

    payload = service.refresh_live_jobs(
        include_web=True,
        include_sponsors=True,
        include_rejected=False,
        web_max_results=5,
        sponsor_max_companies=5,
        sponsor_max_results=5,
    )

    assert payload["jobs"][0]["is_h1b_sponsor"] is True
    assert payload["jobs"][0]["h1b_sponsor_employer"] == "Google LLC"
    assert any("H1B sponsor signal" in signal for signal in payload["jobs"][0]["quality_signals"])


def test_refresh_live_jobs_fetches_live_jd_before_recommending_feed_rows(tmp_path, monkeypatch) -> None:
    targets_path = tmp_path / "targets.json"
    cache_path = tmp_path / "latest_jobs.json"
    targets_path.write_text("[]", encoding="utf-8")
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(targets_path),
        cache_path=str(cache_path),
    )
    monkeypatch.setattr(
        service.web,
        "search_jobs",
        lambda **_kwargs: [
            {
                "job_id": "simplify_amazon",
                "company": "Amazon",
                "title": "Data Engineer I",
                "jd_text": "Listed in a 2026 new-grad roles feed. Open the original posting for full responsibilities and qualifications.",
                "discovered_url": "https://amazon.jobs/en/jobs/10410579/data-engineer-i",
                "source": "Web Feed: Simplify New Grad",
                "location": "Seattle, WA",
                "posted_at": "2d",
            }
        ],
    )
    monkeypatch.setattr(
        service,
        "fetch_job_description",
        lambda _url: "Basic Qualifications: 2+ years of data engineering experience. Experience building ETL pipelines.",
    )
    monkeypatch.setattr(
        service,
        "_job_availability",
        lambda _url: ("active", "Posting page is reachable."),
    )

    payload = service.refresh_live_jobs(include_web=True, include_rejected=False, web_max_results=5)

    assert payload["fresh_job_count"] == 0
    assert payload["all_jobs"][0]["jd_text_source"] == "live_posting"
    assert payload["all_jobs"][0]["quality_decision"] == "reject"
    assert payload["all_jobs"][0]["years_required"] == 2


def test_refresh_live_jobs_preserves_existing_recommendations_when_sources_return_empty(tmp_path, monkeypatch) -> None:
    targets_path = tmp_path / "targets.json"
    cache_path = tmp_path / "latest_jobs.json"
    targets_path.write_text("[]", encoding="utf-8")
    cache_path.write_text(
        """
        {
          "jobs": [
            {
              "job_id": "existing_good",
              "company": "ExistingCo",
              "title": "Junior Data Scientist",
              "discovered_url": "https://example.com/existing",
              "source": "previous cache"
            }
          ],
          "all_jobs": [
            {
              "job_id": "existing_good",
              "company": "ExistingCo",
              "title": "Junior Data Scientist",
              "discovered_url": "https://example.com/existing",
              "source": "previous cache"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(targets_path),
        cache_path=str(cache_path),
    )
    monkeypatch.setattr(service.web, "search_jobs", lambda **_kwargs: [])

    payload = service.refresh_live_jobs(include_web=True, include_rejected=False, web_max_results=5)

    assert payload["fresh_job_count"] == 0
    assert payload["preserved_job_count"] == 1
    assert payload["jobs"][0]["job_id"] == "existing_good"
    assert service.load_cached_jobs(limit=10)[0]["job_id"] == "existing_good"


def test_refresh_live_jobs_drops_preserved_jobs_that_are_no_longer_available(tmp_path, monkeypatch) -> None:
    targets_path = tmp_path / "targets.json"
    cache_path = tmp_path / "latest_jobs.json"
    targets_path.write_text("[]", encoding="utf-8")
    cache_path.write_text(
        """
        {
          "jobs": [
            {
              "job_id": "dead_greenhouse",
              "company": "DeadCo",
              "title": "Junior Data Scientist",
              "jd_text": "Build Python SQL machine learning models. 1 year experience.",
              "discovered_url": "https://job-boards.greenhouse.io/deadco/jobs/123",
              "source": "Greenhouse Live Feed",
              "location": "Remote, United States",
              "quality_actionable": true,
              "quality_decision": "pass"
            }
          ],
          "all_jobs": []
        }
        """,
        encoding="utf-8",
    )
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(targets_path),
        cache_path=str(cache_path),
    )
    monkeypatch.setattr(service.web, "search_jobs", lambda **_kwargs: [])
    monkeypatch.setattr(
        service,
        "_job_availability",
        lambda _url: ("inactive", "Greenhouse posting is no longer listed in the board API."),
    )

    payload = service.refresh_live_jobs(include_web=True, include_rejected=False, web_max_results=5)

    assert payload["fresh_job_count"] == 0
    assert payload["preserved_job_count"] == 0
    assert payload["jobs"] == []


def test_refresh_live_jobs_does_not_preserve_stale_cached_recommendations(tmp_path, monkeypatch) -> None:
    targets_path = tmp_path / "targets.json"
    cache_path = tmp_path / "latest_jobs.json"
    targets_path.write_text("[]", encoding="utf-8")
    stale_posted_at = (datetime.now(UTC) - timedelta(days=45)).isoformat()
    cache_path.write_text(
        f"""
        {{
          "jobs": [
            {{
              "job_id": "existing_stale",
              "company": "StaleCo",
              "title": "Junior Data Scientist",
              "discovered_url": "https://example.com/stale",
              "source": "previous cache",
              "posted_at": "{stale_posted_at}"
            }}
          ],
          "all_jobs": []
        }}
        """,
        encoding="utf-8",
    )
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(targets_path),
        cache_path=str(cache_path),
    )
    monkeypatch.setattr(service.web, "search_jobs", lambda **_kwargs: [])

    payload = service.refresh_live_jobs(include_web=True, include_rejected=False, web_max_results=5)

    assert payload["fresh_job_count"] == 0
    assert payload["preserved_job_count"] == 0
    assert payload["jobs"] == []


def test_refresh_live_jobs_keeps_fresh_jobs_first_then_previous_recommendations(tmp_path, monkeypatch) -> None:
    targets_path = tmp_path / "targets.json"
    cache_path = tmp_path / "latest_jobs.json"
    targets_path.write_text("[]", encoding="utf-8")
    cache_path.write_text(
        """
        {
          "jobs": [
            {
              "job_id": "existing_good",
              "company": "ExistingCo",
              "title": "Junior Data Scientist",
              "discovered_url": "https://example.com/existing",
              "source": "previous cache"
            }
          ],
          "all_jobs": []
        }
        """,
        encoding="utf-8",
    )
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(targets_path),
        cache_path=str(cache_path),
    )
    monkeypatch.setattr(
        service.web,
        "search_jobs",
        lambda **_kwargs: [
            {
                "job_id": "fresh_good",
                "company": "FreshCo",
                "title": "Junior Data Scientist",
                "jd_text": "Python SQL machine learning. 1 year experience.",
                "discovered_url": "https://example.com/fresh",
                "source": "Web Search: example.com",
                "location": "Remote, United States",
            }
        ],
    )

    payload = service.refresh_live_jobs(include_web=True, include_rejected=False, web_max_results=5)

    assert [job["job_id"] for job in payload["jobs"]] == ["fresh_good", "existing_good"]


def test_refresh_recent_jobs_preserves_still_fresh_cache_without_touching_main_cache(tmp_path, monkeypatch) -> None:
    targets_path = tmp_path / "targets.json"
    cache_path = tmp_path / "latest_jobs.json"
    recent_cache_path = tmp_path / "recent_24h_jobs.json"
    targets_path.write_text("[]", encoding="utf-8")
    cache_path.write_text('{"jobs": [{"job_id": "main_cache"}]}', encoding="utf-8")
    now = datetime.now(UTC)
    recent_cache_path.write_text(
        f"""
        {{
          "jobs": [
            {{
              "job_id": "cached_fresh",
              "company": "CachedCo",
              "title": "Junior Data Scientist",
              "discovered_url": "https://example.com/cached-fresh",
              "source": "previous fresh cache",
              "posted_at": "{(now - timedelta(hours=3)).isoformat()}"
            }},
            {{
              "job_id": "cached_stale",
              "company": "StaleCo",
              "title": "Junior Data Scientist",
              "discovered_url": "https://example.com/cached-stale",
              "source": "previous fresh cache",
              "posted_at": "{(now - timedelta(hours=30)).isoformat()}"
            }}
          ],
          "all_jobs": []
        }}
        """,
        encoding="utf-8",
    )
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(targets_path),
        cache_path=str(cache_path),
        recent_cache_path=str(recent_cache_path),
    )
    monkeypatch.setattr(service.web, "search_recent_jobs", lambda **_kwargs: [])

    payload = service.refresh_recent_jobs(hours=24, max_results=5, include_rejected=False)

    assert payload["fresh_job_count"] == 0
    assert payload["preserved_job_count"] == 1
    assert [job["job_id"] for job in payload["jobs"]] == ["cached_fresh"]
    assert service.load_cached_jobs(limit=10)[0]["job_id"] == "main_cache"


def test_refresh_recent_jobs_keeps_new_results_before_cached_recent_jobs(tmp_path, monkeypatch) -> None:
    targets_path = tmp_path / "targets.json"
    cache_path = tmp_path / "latest_jobs.json"
    recent_cache_path = tmp_path / "recent_24h_jobs.json"
    targets_path.write_text("[]", encoding="utf-8")
    now = datetime.now(UTC)
    recent_cache_path.write_text(
        f"""
        {{
          "jobs": [
            {{
              "job_id": "cached_fresh",
              "company": "CachedCo",
              "title": "Junior Data Scientist",
              "discovered_url": "https://example.com/cached-fresh",
              "source": "previous fresh cache",
              "posted_at": "{(now - timedelta(hours=4)).isoformat()}"
            }}
          ]
        }}
        """,
        encoding="utf-8",
    )
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(targets_path),
        cache_path=str(cache_path),
        recent_cache_path=str(recent_cache_path),
    )
    monkeypatch.setattr(
        service.web,
        "search_recent_jobs",
        lambda **_kwargs: [
            {
                "job_id": "new_fresh",
                "company": "FreshCo",
                "title": "Junior Data Scientist",
                "jd_text": "Python SQL machine learning. 1 year experience.",
                "discovered_url": "https://example.com/new-fresh",
                "source": "Web Feed: Example",
                "location": "Remote, United States",
                "posted_at": (now - timedelta(hours=1)).isoformat(),
                "freshness_hours": 1,
                "freshness_label": "1h",
            }
        ],
    )

    payload = service.refresh_recent_jobs(hours=24, max_results=5, include_rejected=False)

    assert [job["job_id"] for job in payload["jobs"]] == ["new_fresh", "cached_fresh"]


def test_refresh_recent_jobs_does_not_preserve_cached_rejects_by_default(tmp_path, monkeypatch) -> None:
    targets_path = tmp_path / "targets.json"
    cache_path = tmp_path / "latest_jobs.json"
    recent_cache_path = tmp_path / "recent_24h_jobs.json"
    targets_path.write_text("[]", encoding="utf-8")
    now = datetime.now(UTC)
    recent_cache_path.write_text(
        f"""
        {{
          "jobs": [
            {{
              "job_id": "cached_reject",
              "company": "RejectCo",
              "title": "Senior Data Scientist",
              "discovered_url": "https://example.com/cached-reject",
              "source": "previous fresh cache",
              "posted_at": "{(now - timedelta(hours=3)).isoformat()}",
              "quality_decision": "reject",
              "quality_actionable": false
            }}
          ]
        }}
        """,
        encoding="utf-8",
    )
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(targets_path),
        cache_path=str(cache_path),
        recent_cache_path=str(recent_cache_path),
    )
    monkeypatch.setattr(service.web, "search_recent_jobs", lambda **_kwargs: [])

    payload = service.refresh_recent_jobs(hours=24, max_results=5, include_rejected=False)

    assert payload["preserved_job_count"] == 0
    assert payload["jobs"] == []


def test_refresh_recent_jobs_includes_recent_target_sources(tmp_path, monkeypatch) -> None:
    targets_path = tmp_path / "targets.json"
    cache_path = tmp_path / "latest_jobs.json"
    recent_cache_path = tmp_path / "recent_24h_jobs.json"
    targets_path.write_text(
        """
        [
          {"company": "TargetCo", "ats_type": "greenhouse", "url": "https://job-boards.greenhouse.io/targetco"}
        ]
        """,
        encoding="utf-8",
    )
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(targets_path),
        cache_path=str(cache_path),
        recent_cache_path=str(recent_cache_path),
    )
    monkeypatch.setattr(service.web, "search_recent_jobs", lambda **_kwargs: [])
    monkeypatch.setattr(
        service,
        "_scrape_recent_target",
        lambda *_args, **_kwargs: [
            {
                "job_id": "target_fresh",
                "company": "TargetCo",
                "title": "Junior Data Scientist",
                "jd_text": "Python SQL machine learning. 1 year experience.",
                "discovered_url": "https://example.com/target-fresh",
                "source": "Greenhouse Fresh Feed",
                "location": "Remote, United States",
                "posted_at": datetime.now(UTC).isoformat(),
            }
        ],
    )

    payload = service.refresh_recent_jobs(hours=24, max_results=5, include_rejected=False, max_target_companies=1)

    assert payload["targets"][0]["ats_type"] == "web_recent"
    assert payload["targets"][1]["company"] == "TargetCo"
    assert payload["targets"][1]["scraped"] == 1
    assert payload["jobs"][0]["job_id"] == "target_fresh"


def test_ensure_jd_text_replaces_simplify_placeholder_before_quality_gate(tmp_path, monkeypatch) -> None:
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(tmp_path / "targets.json"),
        cache_path=str(tmp_path / "latest_jobs.json"),
    )
    monkeypatch.setattr(
        service,
        "fetch_job_description",
        lambda _url: "Basic Qualifications: 2+ years of data engineering experience. Experience building ETL pipelines.",
    )
    monkeypatch.setattr(
        service,
        "_job_availability",
        lambda _url: ("active", "Posting page is reachable."),
    )
    job = {
        "job_id": "simplify_amazon",
        "company": "Amazon",
        "title": "Data Engineer I",
        "jd_text": "Listed in a 2026 new-grad roles feed. Open the original posting for full responsibilities and qualifications.",
        "discovered_url": "https://amazon.jobs/en/jobs/10410579/data-engineer-i",
        "source": "Web Feed: Simplify New Grad",
        "location": "Seattle, WA",
    }

    enriched = service.ensure_jd_text(job)

    assert enriched["jd_text_source"] == "live_posting"
    assert enriched["years_required"] == 2
    assert enriched["quality_decision"] == "reject"
    assert enriched["quality_actionable"] is False


def test_fetch_job_description_uses_workday_meta_description_when_body_is_empty(tmp_path) -> None:
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(tmp_path / "targets.json"),
        cache_path=str(tmp_path / "latest_jobs.json"),
    )
    html = """
    <html>
      <head>
        <meta property="og:description" content="Applicants must be authorized to work for ANY employer in the U.S. The company does not sponsor/support H-1B petitions, TN, or Forms I-983/STEM OPT, for this role.">
      </head>
      <body></body>
    </html>
    """

    text = service._extract_text(html)

    assert "does not sponsor/support H-1B" in text
    assert "I-983/STEM OPT" in text


def test_enrich_job_drops_stale_ai_when_new_gate_rejects(tmp_path) -> None:
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(tmp_path / "targets.json"),
        cache_path=str(tmp_path / "latest_jobs.json"),
    )
    job = {
        "job_id": "stale_ai",
        "company": "Travelers",
        "title": "Data Engineer I",
        "jd_text": "The company does not sponsor/support H-1B petitions, TN, or Forms I-983/STEM OPT, for this role.",
        "location": "Atlanta, GA",
        "source": "pytest",
        "ai_score": 83,
        "ai_verdict": "good_match",
    }

    enriched = service.ensure_jd_text(job)

    assert enriched["quality_decision"] == "reject"
    assert "ai_score" not in enriched
    assert "ai_verdict" not in enriched


def test_enrich_job_rejects_search_listing_pages(tmp_path) -> None:
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(tmp_path / "targets.json"),
        cache_path=str(tmp_path / "latest_jobs.json"),
    )

    enriched = service.ensure_jd_text(
        {
            "job_id": "listing_page",
            "company": "RemoteRocketship",
            "title": "38 Remote Junior Data Scientist Jobs in the United States",
            "jd_text": "38 Remote Junior Data Scientist Jobs in the United States. Browse jobs and apply to open roles.",
            "discovered_url": "https://www.remoterocketship.com/country/united-states/jobs/junior-data-scientist",
            "source": "Web Search: remoterocketship.com",
            "location": "Remote",
        }
    )

    assert enriched["quality_decision"] == "reject"
    assert any("listing/search page" in blocker for blocker in enriched["quality_blockers"])


def test_enrich_job_rejects_public_remote_feed_without_us_scope(tmp_path) -> None:
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(tmp_path / "targets.json"),
        cache_path=str(tmp_path / "latest_jobs.json"),
    )

    enriched = service.ensure_jd_text(
        {
            "job_id": "remoteok_ambiguous",
            "company": "RemoteCo",
            "title": "Data Analyst",
            "jd_text": "Build dashboards with Python and SQL for a remote analytics team. 1 year experience.",
            "discovered_url": "https://remoteok.com/remote-jobs/remote-data-analyst-remoteco",
            "source": "Web Feed: RemoteOK",
            "location": "Remote",
        }
    )

    assert enriched["quality_decision"] == "reject"
    assert any("United States eligibility" in blocker for blocker in enriched["quality_blockers"])


def test_enrich_job_rejects_structured_clearance_and_experience_blockers(tmp_path) -> None:
    service = JobFeedService(
        quality_gate=JobQualityGateService(),
        targets_path=str(tmp_path / "targets.json"),
        cache_path=str(tmp_path / "latest_jobs.json"),
    )

    job = {
        "job_id": "structured_blocked",
        "company": "DefenseAI",
        "title": "Junior Data Scientist",
        "jd_text": "Python SQL machine learning role in United States.",
        "location": "United States",
        "source": "Web Feed: Example",
        "is_clearance_required": True,
        "min_years_required": 2,
    }

    enriched = service.ensure_jd_text(job)

    assert enriched["quality_decision"] == "reject"
    assert enriched["quality_actionable"] is False
    assert any("clearance" in blocker.lower() for blocker in enriched["quality_blockers"])
    assert any("experience" in blocker.lower() for blocker in enriched["quality_blockers"])
