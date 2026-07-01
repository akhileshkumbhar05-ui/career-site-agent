from __future__ import annotations

import hashlib
from urllib.parse import urlparse
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


USER_AGENT = "CareerSiteAgent/1.0"
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


class GreenhouseScraper:
    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def scrape_jobs(
        self,
        company: str,
        board_url: str,
        source: str = "Greenhouse Scraper",
        max_jobs: int | None = None,
        filter_relevant: bool = True,
    ) -> list[dict]:
        board_token = self._board_token(board_url)
        if board_token:
            try:
                api_jobs = self._scrape_jobs_api(
                    company=company,
                    board_token=board_token,
                    source=source,
                    max_jobs=max_jobs,
                    filter_relevant=filter_relevant,
                )
                if api_jobs:
                    return api_jobs
            except Exception:
                pass

        html, final_url = self._fetch_text_with_final_url(board_url)
        jobs = self._extract_job_cards(
            company=company,
            board_url=final_url,
            html=html,
            source=source,
            max_jobs=max_jobs,
            filter_relevant=filter_relevant,
        )
        return jobs

    def _scrape_jobs_api(
        self,
        *,
        company: str,
        board_token: str,
        source: str,
        max_jobs: int | None = None,
        filter_relevant: bool = True,
    ) -> list[dict]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()

        jobs: list[dict] = []
        seen_urls: set[str] = set()
        for item in payload.get("jobs", []):
            title = str(item.get("title") or "").strip()
            absolute_url = str(item.get("absolute_url") or "").strip()
            if not title or not absolute_url or absolute_url in seen_urls:
                continue

            jd_text = self._extract_job_description(str(item.get("content") or ""))
            if not jd_text:
                continue
            if filter_relevant and not self._is_relevant_job(title, jd_text):
                continue

            seen_urls.add(absolute_url)
            company_name = str(item.get("company_name") or company or "Unknown Company").strip()
            jobs.append(
                {
                    "job_id": self._make_job_id(company=company_name, title=title, url=absolute_url),
                    "company": company_name,
                    "title": title,
                    "jd_text": jd_text,
                    "discovered_url": absolute_url,
                    "url": absolute_url,
                    "source": source,
                    "location": self._location_name(item),
                    "posted_at": item.get("first_published") or item.get("updated_at"),
                    "updated_at": item.get("updated_at"),
                }
            )

            if max_jobs is not None and len(jobs) >= max_jobs:
                break

        return jobs

    def _fetch_text(self, url: str) -> str:
        text, _ = self._fetch_text_with_final_url(url)
        return text

    def _fetch_text_with_final_url(self, url: str) -> tuple[str, str]:
        headers = {"User-Agent": USER_AGENT}
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text, str(response.url)

    def _extract_job_cards(
        self,
        company: str,
        board_url: str,
        html: str,
        source: str,
        max_jobs: int | None = None,
        filter_relevant: bool = True,
    ) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")

        anchors = soup.select("a[href]")
        jobs: list[dict] = []
        seen_urls: set[str] = set()

        for a in anchors:
            href = (a.get("href") or "").strip()
            title = a.get_text(" ", strip=True)

            if not href or not title:
                continue

            absolute_url = urljoin(board_url, href)

            if not self._is_greenhouse_job_url(absolute_url):
                continue

            if absolute_url in seen_urls:
                continue

            jd_text = self._safe_fetch_job_description(absolute_url)
            if not jd_text:
                continue
            if filter_relevant and not self._is_relevant_job(title, jd_text):
                continue

            seen_urls.add(absolute_url)

            job_id = self._make_job_id(company=company, title=title, url=absolute_url)

            jobs.append(
                {
                    "job_id": job_id,
                    "company": company,
                    "title": title,
                    "jd_text": jd_text,
                    "discovered_url": absolute_url,
                    "source": source,
                }
            )

            if max_jobs is not None and len(jobs) >= max_jobs:
                break

        return jobs

    def _safe_fetch_job_description(self, job_url: str) -> str:
        try:
            html = self._fetch_text(job_url)
            return self._extract_job_description(html)
        except Exception:
            return ""

    def _extract_job_description(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")

        preferred_selectors = [
            ".content",
            "#content",
            ".job__description",
            ".job-post",
            ".job-post-content",
            ".opening",
            "section",
            "main",
        ]

        texts: list[str] = []

        for selector in preferred_selectors:
            nodes = soup.select(selector)
            for node in nodes:
                text = node.get_text("\n", strip=True)
                if len(text) > 500:
                    texts.append(text)

            if texts:
                break

        if not texts:
            body_text = soup.get_text("\n", strip=True)
            return body_text[:15000]

        merged = "\n\n".join(texts)
        return merged[:15000]

    def _make_job_id(self, company: str, title: str, url: str) -> str:
        raw = f"{company}|{title}|{url}".encode("utf-8")
        digest = hashlib.md5(raw).hexdigest()[:12]
        company_slug = company.lower().replace(" ", "_").replace("/", "_")
        return f"{company_slug}_{digest}"

    @staticmethod
    def _board_token(board_url: str) -> str:
        parsed = urlparse(board_url)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        return parts[0] if parts else ""

    @staticmethod
    def _location_name(item: dict) -> str:
        location = item.get("location") or {}
        if isinstance(location, dict):
            return str(location.get("name") or "")
        return str(location or "")

    @staticmethod
    def _is_greenhouse_job_url(url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.lower()

        if not host.endswith("greenhouse.io"):
            return False

        return "/jobs/" in path

    @staticmethod
    def _is_relevant_job(title: str, jd_text: str) -> bool:
        title_text = title.lower()
        combined = f"{title_text}\n{jd_text.lower()}"
        if any(term in title_text for term in TITLE_RELEVANCE_TERMS):
            return True

        role_surface = any(term in title_text for term in ("analyst", "engineer", "scientist", "developer"))
        return role_surface and any(term in combined for term in BODY_RELEVANCE_TERMS)
