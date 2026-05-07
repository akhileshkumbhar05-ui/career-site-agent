from __future__ import annotations

import hashlib
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


USER_AGENT = "CareerSiteAgent/1.0"


class GreenhouseScraper:
    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def scrape_jobs(self, company: str, board_url: str, source: str = "Greenhouse Scraper") -> list[dict]:
        html = self._fetch_text(board_url)
        jobs = self._extract_job_cards(company=company, board_url=board_url, html=html, source=source)
        return jobs

    def _fetch_text(self, url: str) -> str:
        headers = {"User-Agent": USER_AGENT}
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text

    def _extract_job_cards(self, company: str, board_url: str, html: str, source: str) -> list[dict]:
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

            if "/jobs/" not in absolute_url and "job-boards.greenhouse.io" not in absolute_url:
                continue

            if absolute_url in seen_urls:
                continue

            jd_text = self._safe_fetch_job_description(absolute_url)
            if not jd_text:
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