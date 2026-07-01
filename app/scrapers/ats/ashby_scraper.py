from __future__ import annotations

import hashlib
import re

import httpx
from bs4 import BeautifulSoup


USER_AGENT = "CareerSiteAgent/1.0"
ASHBY_API_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"

TITLE_RELEVANCE_TERMS = (
    "ai engineer",
    "analytics engineer",
    "applied scientist",
    "artificial intelligence",
    "bi analyst",
    "business analyst",
    "computer vision",
    "data analyst",
    "data analytics",
    "data engineer",
    "data science",
    "data scientist",
    "decision scientist",
    "generative ai",
    "llm engineer",
    "machine learning",
    "ml engineer",
    "python developer",
    "software engineer ai",
)
BODY_RELEVANCE_TERMS = (
    "analytics",
    "computer vision",
    "data pipeline",
    "data pipelines",
    "data science",
    "databricks",
    "etl",
    "generative ai",
    "llm",
    "machine learning",
    "ml",
    "python",
    "pyspark",
    "rag",
    "sql",
)


class AshbyScraper:
    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def scrape_jobs(
        self,
        company: str,
        ashby_slug: str,
        source: str = "Ashby Live Feed",
        filter_relevant: bool = True,
        max_jobs: int | None = None,
    ) -> list[dict]:
        url = ASHBY_API_URL.format(slug=ashby_slug)
        with httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()

        raw_jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        jobs: list[dict] = []
        seen_urls: set[str] = set()
        for item in raw_jobs:
            if not isinstance(item, dict) or item.get("isListed") is False:
                continue

            title = self._clean_text(str(item.get("title") or ""))
            job_url = str(item.get("jobUrl") or item.get("applyUrl") or "").strip()
            jd_text = self._extract_description(str(item.get("descriptionHtml") or ""))
            if not title or not job_url or not jd_text or job_url in seen_urls:
                continue
            if filter_relevant and not self._is_relevant_job(title, jd_text):
                continue

            seen_urls.add(job_url)
            jobs.append(
                {
                    "job_id": self._make_job_id(company=company, title=title, url=job_url),
                    "company": company,
                    "title": title,
                    "jd_text": jd_text,
                    "discovered_url": job_url,
                    "url": job_url,
                    "apply_url": str(item.get("applyUrl") or ""),
                    "source": source,
                    "location": self._location_text(item),
                    "posted_at": item.get("publishedAt") or "",
                    "published_at": item.get("publishedAt") or "",
                    "updated_at": item.get("updatedAt") or item.get("publishedAt") or "",
                }
            )
            if max_jobs is not None and len(jobs) >= max_jobs:
                break

        return jobs

    @staticmethod
    def _extract_description(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        return re.sub(r"\n{3,}", "\n\n", text).strip()[:15000]

    @staticmethod
    def _location_text(item: dict) -> str:
        locations: list[str] = []
        primary = str(item.get("location") or "").strip()
        if primary:
            locations.append(primary)

        for secondary in item.get("secondaryLocations") or []:
            if not isinstance(secondary, dict):
                continue
            location = str(secondary.get("location") or "").strip()
            if location:
                locations.append(location)

        address = item.get("address") if isinstance(item.get("address"), dict) else {}
        postal = address.get("postalAddress") if isinstance(address.get("postalAddress"), dict) else {}
        country = str(postal.get("addressCountry") or "").strip()
        if country:
            locations.append(country)

        unique: list[str] = []
        seen: set[str] = set()
        for location in locations:
            key = location.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(location)
        return ", ".join(unique)

    @staticmethod
    def _make_job_id(company: str, title: str, url: str) -> str:
        raw = f"{company}|{title}|{url}".encode("utf-8")
        digest = hashlib.md5(raw).hexdigest()[:12]
        slug = company.lower().replace(" ", "_").replace("/", "_")
        return f"{slug}_{digest}"

    @staticmethod
    def _is_relevant_job(title: str, jd_text: str) -> bool:
        title_text = title.lower()
        combined = f"{title_text}\n{jd_text.lower()}"
        if any(term in title_text for term in TITLE_RELEVANCE_TERMS):
            return True

        role_surface = any(term in title_text for term in ("analyst", "engineer", "scientist", "developer"))
        return role_surface and any(term in combined for term in BODY_RELEVANCE_TERMS)

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()
