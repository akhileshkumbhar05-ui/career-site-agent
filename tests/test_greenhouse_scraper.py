from app.scrapers.ats.greenhouse_scraper import GreenhouseScraper


def test_greenhouse_scraper_prefers_public_board_api(monkeypatch):
    scraper = GreenhouseScraper()

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "jobs": [
                    {
                        "title": "Junior Data Scientist",
                        "absolute_url": "https://job-boards.greenhouse.io/example/jobs/123",
                        "content": "<div>Responsibilities include Python, SQL, machine learning, and analytics.</div>",
                        "location": {"name": "Remote, United States"},
                        "first_published": "2026-06-07T12:00:00Z",
                        "updated_at": "2026-06-07T12:30:00Z",
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, url: str) -> FakeResponse:
            assert url == "https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true"
            return FakeResponse()

    monkeypatch.setattr("app.scrapers.ats.greenhouse_scraper.httpx.Client", FakeClient)
    monkeypatch.setattr(scraper, "_fetch_text_with_final_url", lambda _url: (_ for _ in ()).throw(AssertionError("HTML fallback should not run")))

    jobs = scraper.scrape_jobs(
        company="Example",
        board_url="https://job-boards.greenhouse.io/example",
        source="pytest",
    )

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Junior Data Scientist"
    assert jobs[0]["location"] == "Remote, United States"
    assert jobs[0]["posted_at"] == "2026-06-07T12:00:00Z"


def test_greenhouse_scraper_filters_irrelevant_api_jobs_before_limit(monkeypatch):
    scraper = GreenhouseScraper()

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "jobs": [
                    {
                        "title": "Account Executive",
                        "absolute_url": "https://job-boards.greenhouse.io/example/jobs/sales",
                        "content": "<div>Own enterprise sales and revenue growth.</div>",
                        "location": {"name": "Remote, United States"},
                    },
                    {
                        "title": "Junior Data Scientist",
                        "absolute_url": "https://job-boards.greenhouse.io/example/jobs/data",
                        "content": "<div>Build machine learning models with Python and SQL.</div>",
                        "location": {"name": "Remote, United States"},
                    },
                    {
                        "title": "Machine Learning Engineer",
                        "absolute_url": "https://job-boards.greenhouse.io/example/jobs/ml",
                        "content": "<div>Build ML systems.</div>",
                        "location": {"name": "Remote, United States"},
                    },
                ]
            }

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, _url: str) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("app.scrapers.ats.greenhouse_scraper.httpx.Client", FakeClient)
    monkeypatch.setattr(scraper, "_fetch_text_with_final_url", lambda _url: (_ for _ in ()).throw(AssertionError("HTML fallback should not run")))

    jobs = scraper.scrape_jobs(
        company="Example",
        board_url="https://job-boards.greenhouse.io/example",
        source="pytest",
        max_jobs=1,
    )

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Junior Data Scientist"


def test_greenhouse_scraper_ignores_non_job_links_on_redirected_pages(monkeypatch):
    scraper = GreenhouseScraper()
    html = """
    <html>
      <body>
        <a href="/careers/jobs/">Marketing careers page</a>
        <a href="https://job-boards.greenhouse.io/example/jobs/123">Junior Data Scientist</a>
      </body>
    </html>
    """

    monkeypatch.setattr(scraper, "_safe_fetch_job_description", lambda url: "Python SQL machine learning")

    jobs = scraper._extract_job_cards(
        company="Example",
        board_url="https://www.example.com/careers/jobs/",
        html=html,
        source="pytest",
    )

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Junior Data Scientist"
    assert jobs[0]["discovered_url"] == "https://job-boards.greenhouse.io/example/jobs/123"


def test_greenhouse_job_url_requires_greenhouse_jobs_path():
    assert GreenhouseScraper._is_greenhouse_job_url("https://job-boards.greenhouse.io/example/jobs/123")
    assert not GreenhouseScraper._is_greenhouse_job_url("https://job-boards.greenhouse.io/example")
    assert not GreenhouseScraper._is_greenhouse_job_url("https://www.cloudflare.com/careers/jobs/")
