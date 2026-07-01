from __future__ import annotations

import hashlib
import logging
import re

import httpx

logger = logging.getLogger(__name__)

LEVER_API_URL = "https://api.lever.co/v0/postings/{company}?mode=json"
USER_AGENT = "CareerSiteAgent/1.0"

RELEVANT_KEYWORDS = {
    "ai",
    "analyst",
    "analytics",
    "artificial intelligence",
    "data",
    "deep learning",
    "engineer",
    "intelligence",
    "machine learning",
    "ml",
    "nlp",
    "research",
    "scientist",
}


class LeverScraper:
    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def scrape_jobs(
        self,
        company: str,
        lever_slug: str,
        source: str = "Lever Scraper",
        filter_relevant: bool = True,
        max_jobs: int | None = None,
    ) -> list[dict]:
        url = LEVER_API_URL.format(company=lever_slug)

        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                postings = response.json()
        except Exception as exc:
            logger.error("Lever scrape failed for %s (%s): %s", company, lever_slug, exc)
            return []

        if not isinstance(postings, list):
            logger.warning("Unexpected Lever response for %s", company)
            return []

        jobs: list[dict] = []
        for posting in postings:
            title = posting.get("text", "")
            categories = posting.get("categories", {}) or {}
            team = categories.get("team", "")
            location = categories.get("location", "")
            posting_url = posting.get("hostedUrl", "")

            if filter_relevant and not self._is_relevant(title=title, team=team):
                continue

            jd_text = self._extract_jd(posting)
            if not title or not posting_url or not jd_text:
                continue

            jobs.append(
                {
                    "job_id": self._make_job_id(company, title, posting_url),
                    "company": company,
                    "title": title,
                    "jd_text": jd_text,
                    "discovered_url": posting_url,
                    "source": source,
                    "location": location,
                    "posted_at": posting.get("createdAt", ""),
                }
            )
            if max_jobs is not None and len(jobs) >= max_jobs:
                break

        logger.info("Lever scrape found %d relevant jobs for %s", len(jobs), company)
        return jobs

    @staticmethod
    def _is_relevant(title: str, team: str) -> bool:
        combined = f"{title} {team}".lower()
        return any(keyword in combined for keyword in RELEVANT_KEYWORDS)

    @staticmethod
    def _extract_jd(posting: dict) -> str:
        content_parts: list[str] = []

        content_html = posting.get("content", "")
        if content_html:
            content_parts.append(_strip_html(content_html))

        for section in posting.get("lists", []):
            heading = section.get("text", "")
            content = section.get("content", "")
            if heading:
                content_parts.append(heading)
            if content:
                content_parts.append(_strip_html(content))

        return "\n\n".join(part for part in content_parts if part).strip()[:15000]

    @staticmethod
    def _make_job_id(company: str, title: str, url: str) -> str:
        raw = f"{company}|{title}|{url}".encode("utf-8")
        digest = hashlib.md5(raw).hexdigest()[:12]
        slug = company.lower().replace(" ", "_").replace("/", "_")
        return f"{slug}_{digest}"


def _strip_html(value: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", clean).strip()
