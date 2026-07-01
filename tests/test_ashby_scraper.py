from app.scrapers.ats.ashby_scraper import AshbyScraper


def test_ashby_scraper_reads_public_posting_api(monkeypatch):
    scraper = AshbyScraper()

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "jobs": [
                    {
                        "id": "job-1",
                        "title": "RevOps Analyst (Analytics)",
                        "isListed": True,
                        "location": "New York",
                        "secondaryLocations": [{"location": "San Francisco"}],
                        "address": {"postalAddress": {"addressCountry": "United States"}},
                        "publishedAt": "2026-06-07T12:00:00Z",
                        "jobUrl": "https://jobs.ashbyhq.com/example/job-1",
                        "applyUrl": "https://jobs.ashbyhq.com/example/job-1/application",
                        "descriptionHtml": "<p>Build analytics systems with Python, SQL, and data pipelines.</p>",
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
            assert url == "https://api.ashbyhq.com/posting-api/job-board/example"
            return FakeResponse()

    monkeypatch.setattr("app.scrapers.ats.ashby_scraper.httpx.Client", FakeClient)

    jobs = scraper.scrape_jobs(company="Example", ashby_slug="example", source="pytest")

    assert len(jobs) == 1
    assert jobs[0]["title"] == "RevOps Analyst (Analytics)"
    assert jobs[0]["location"] == "New York, San Francisco, United States"
    assert jobs[0]["posted_at"] == "2026-06-07T12:00:00Z"


def test_ashby_scraper_filters_irrelevant_jobs_before_limit(monkeypatch):
    scraper = AshbyScraper()

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "jobs": [
                    {
                        "title": "Account Executive",
                        "isListed": True,
                        "location": "Remote",
                        "jobUrl": "https://jobs.ashbyhq.com/example/sales",
                        "descriptionHtml": "<p>Own sales pipeline and customer expansion.</p>",
                    },
                    {
                        "title": "Data Scientist",
                        "isListed": True,
                        "location": "Remote",
                        "jobUrl": "https://jobs.ashbyhq.com/example/data",
                        "descriptionHtml": "<p>Build machine learning models with Python.</p>",
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

    monkeypatch.setattr("app.scrapers.ats.ashby_scraper.httpx.Client", FakeClient)

    jobs = scraper.scrape_jobs(company="Example", ashby_slug="example", max_jobs=1)

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data Scientist"
