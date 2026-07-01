from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BLOCKED_DISCOVERY_DOMAINS = ("jobright.ai",)
DISCOVERY_MAX_AGE_DAYS = 21


class WebJobSearchService:
    """Discovers job pages from broad web search, then normalizes them into job rows."""

    def __init__(self) -> None:
        self.timeout = 18.0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    def search_jobs(self, *, max_results: int = 20) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        source_budget = max(max_results, 30)
        for job in self._search_public_job_feeds(max_results=source_budget, max_age_days=DISCOVERY_MAX_AGE_DAYS):
            normalized = self._normalize_url(str(job.get("discovered_url") or job.get("url") or ""))
            if not normalized or normalized in seen_urls or self._is_blocked_source_url(normalized):
                continue
            seen_urls.add(normalized)
            jobs.append(self._with_discovery_score(job))

        for query in self._queries():
            results = self._search_duckduckgo(query, limit=8)
            if not results:
                results = self._search_bing(query, limit=8)
            for result in results:
                url = result["url"]
                normalized = self._normalize_url(url)
                if not normalized or normalized in seen_urls or not self._looks_like_job_url(normalized):
                    continue
                seen_urls.add(normalized)
                job = self._result_to_job(result)
                if not job:
                    continue
                jobs.append(self._with_discovery_score(job))

        return self._rank_jobs(jobs)[:max_results]

    def search_recent_jobs(self, *, max_results: int = 25, hours: int = 24) -> list[dict[str, Any]]:
        """Return relevant public-feed jobs with a known posted time inside the requested window."""
        now = datetime.now(UTC)
        source_budget = max(max_results * 4, 80)
        recent_jobs: list[dict[str, Any]] = []

        for job in self._search_public_job_feeds(max_results=source_budget):
            age_hours = self._posted_age_hours(self._posted_value(job), now=now)
            if age_hours is None or age_hours > hours:
                continue

            updated = self._with_discovery_score(job)
            updated["freshness_hours"] = round(age_hours, 2)
            updated["freshness_label"] = self._freshness_label(age_hours)
            updated["freshness_window_hours"] = hours
            updated["freshness_checked_at"] = now.isoformat()
            updated["source_scope"] = f"fresh_{hours}h"
            recent_jobs.append(updated)

        return sorted(
            self._dedupe(recent_jobs),
            key=lambda job: (
                int(job.get("discovery_score") or 0),
                -float(job.get("freshness_hours") or 999),
                bool(job.get("jd_text")),
                str(job.get("company") or "").lower(),
            ),
            reverse=True,
        )[:max_results]

    def search_sponsored_entry_jobs(
        self,
        sponsors: list[dict[str, Any]],
        *,
        max_results: int = 30,
        per_company_limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Find explicit early-career target-role jobs at employers with DOL LCA sponsor history."""
        jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for sponsor in sponsors:
            company = str(sponsor.get("employer_name") or "").strip()
            if not company:
                continue

            company_kept = 0
            company_attempts = 0
            for query in self._sponsor_queries(company):
                results = self._search_bing(query, limit=4)
                for result in results:
                    normalized = self._normalize_url(result.get("url", ""))
                    if not normalized or normalized in seen_urls or not self._looks_like_job_url(normalized):
                        continue
                    if self._is_blocked_source_url(normalized):
                        continue
                    result_hint = f"{result.get('title', '')}\n{result.get('snippet', '')}\n{normalized}"
                    if not self._has_explicit_early_career_signal(result_hint):
                        continue

                    company_attempts += 1
                    job = self._result_to_job(result)
                    if not job:
                        continue
                    combined = f"{job.get('title', '')}\n{job.get('jd_text', '')}\n{job.get('search_snippet', '')}"
                    if not self._has_explicit_early_career_signal(combined):
                        continue

                    seen_urls.add(normalized)
                    updated = self._with_discovery_score(self._with_sponsor_metadata(job, sponsor))
                    jobs.append(updated)
                    company_kept += 1
                    if len(jobs) >= max_results:
                        return self._rank_jobs(self._dedupe(jobs))[:max_results]
                    if company_kept >= per_company_limit:
                        break
                    if company_attempts >= per_company_limit * 2:
                        break
                if company_kept >= per_company_limit:
                    break
                if company_attempts >= per_company_limit * 2:
                    break

        return self._rank_jobs(self._dedupe(jobs))[:max_results]

    def _search_public_job_feeds(self, *, max_results: int, max_age_days: int | None = None) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        jobs.extend(self._search_simplify_new_grad(max_results=max_results))
        jobs.extend(self._search_remoteok(max_results=max_results))
        jobs.extend(self._search_himalayas(max_results=max_results))
        jobs.extend(self._search_themuse(max_results=max_results))
        jobs.extend(self._search_remotive(max_results=max_results))
        jobs.extend(self._search_remotejobs_org(max_results=max_results))
        jobs.extend(self._search_arbeitnow(max_results=max_results))
        if max_age_days is not None:
            jobs = [job for job in jobs if self._within_posted_age(job, max_age_days=max_age_days)]
        return self._rank_jobs(self._dedupe(jobs))[:max_results]

    def _with_discovery_score(self, job: dict[str, Any]) -> dict[str, Any]:
        updated = dict(job)
        text = " ".join(
            self._stringify_signal(updated.get(key))
            for key in (
                "title",
                "company",
                "location",
                "jd_text",
                "source",
                "search_query",
                "job_seniority",
                "recommendation_tags",
                "job_tags",
                "skill_summaries",
                "core_responsibilities",
            )
        ).lower()
        title = str(updated.get("title") or "").lower()
        source = str(updated.get("source") or "").lower()
        seniority = str(updated.get("job_seniority") or "").lower()
        score = 20

        if any(term in title for term in ["data scientist", "machine learning", "ml engineer", "ai/ml", "ai engineer"]):
            score += 34
        elif any(term in title for term in ["data analyst", "business analyst", "analytics"]):
            score += 28
        elif "software engineer" in title and any(term in text for term in ["python", "ai", "machine learning", "llm"]):
            score += 24
        elif any(term in text for term in ["python", "sql", "machine learning", "analytics"]):
            score += 14

        if any(term in text for term in ["new grad", "entry level", "early career", "junior", "0-1", "0-2"]):
            score += 22
        if any(term in seniority for term in ["entry", "new grad", "junior"]):
            score += 10
        if "united states" in text or "usa" in text or "remote in usa" in text:
            score += 10
        if "simplify new grad" in source:
            score += 16
        elif any(term in source for term in ["greenhouse", "lever", "ashby", "workday"]):
            score += 8
        if updated.get("is_h1b_sponsor"):
            score += 8
        if any(term in title for term in ["senior", "staff", "principal", "lead", "manager", "director"]):
            score -= 35
        if any(term in seniority for term in ["senior", "staff", "principal", "lead", "manager", "director"]):
            score -= 35
        if updated.get("is_clearance_required") or updated.get("is_citizen_only"):
            score -= 60
        try:
            min_years = float(updated.get("min_years_required"))
        except (TypeError, ValueError):
            min_years = 0.0
        if min_years >= 2:
            score -= 35
        try:
            max_years = float(updated.get("max_years_required"))
        except (TypeError, ValueError):
            max_years = 0.0
        if max_years > 2 and min_years < 2:
            score -= 14
        if any(term in text for term in ["security clearance", "u.s. citizen", "us citizen", "will not sponsor", "no sponsorship"]):
            score -= 45
        if any(term in text for term in ["canada", "norway", "rou", "europe"]) and "united states" not in text and "usa" not in text:
            score -= 18

        updated["discovery_score"] = max(0, min(100, score))
        updated["discovery_bucket"] = (
            "high_fit_source" if updated["discovery_score"] >= 75 else
            "review_source" if updated["discovery_score"] >= 50 else
            "low_fit_source"
        )
        return updated

    @staticmethod
    def _stringify_signal(value: Any) -> str:
        if isinstance(value, list):
            return " ".join(WebJobSearchService._stringify_signal(item) for item in value)
        if isinstance(value, dict):
            return " ".join(WebJobSearchService._stringify_signal(item) for item in value.values())
        return str(value or "")

    def _rank_jobs(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched = [self._with_discovery_score(job) for job in jobs]
        return sorted(
            enriched,
            key=lambda job: (
                int(job.get("discovery_score") or 0),
                "simplify new grad" in str(job.get("source") or "").lower(),
                bool(job.get("jd_text")),
                str(job.get("company") or "").lower(),
            ),
            reverse=True,
        )

    def _search_remoteok(self, *, max_results: int) -> list[dict[str, Any]]:
        url = "https://remoteok.com/api"
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers={**self.headers, "Accept": "application/json"}) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning("RemoteOK job feed failed: %s", exc)
            return []

        jobs: list[dict[str, Any]] = []
        for item in payload[1:] if isinstance(payload, list) else []:
            title = str(item.get("position") or "").strip()
            description = self._clean_html(str(item.get("description") or ""))
            location = str(item.get("location") or "Remote").strip() or "Remote"
            combined = f"{title}\n{description}\n{' '.join(item.get('tags') or [])}"
            if (
                not self._location_ok(location, combined)
                or not self._passes_role_prefilter(title, description)
                or not self._looks_like_job_text(combined)
            ):
                continue
            job_url = str(item.get("url") or item.get("apply_url") or "")
            company = self._clean_text(str(item.get("company") or "Unknown Company"))
            raw_id = "|".join([company, title, job_url])
            jobs.append(
                {
                    "job_id": f"remoteok_{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:18]}",
                    "company": company,
                    "title": self._clean_text(title),
                    "jd_text": description,
                    "discovered_url": job_url,
                    "url": job_url,
                    "source": "Web Feed: RemoteOK",
                    "location": location,
                    "posted_at": item.get("date") or item.get("epoch"),
                    "search_query": "remoteok public feed",
                }
            )
            if len(jobs) >= max_results:
                break
        return jobs

    def _search_himalayas(self, *, max_results: int) -> list[dict[str, Any]]:
        url = "https://himalayas.app/jobs/api?limit=100"
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers={**self.headers, "Accept": "application/json"}) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning("Himalayas job feed failed: %s", exc)
            return []

        jobs: list[dict[str, Any]] = []
        for item in payload.get("jobs", []):
            title = str(item.get("title") or "").strip()
            description = self._clean_html(str(item.get("description") or item.get("excerpt") or ""))
            locations = item.get("locationRestrictions") or []
            location = ", ".join(str(value) for value in locations if value) or "Remote"
            combined = f"{title}\n{description}\n{item.get('excerpt') or ''}"
            if (
                not self._location_ok(location, combined)
                or not self._passes_role_prefilter(title, description)
                or not self._looks_like_job_text(combined)
            ):
                continue
            job_url = str(item.get("applicationLink") or "")
            company = self._clean_text(str(item.get("companyName") or "Unknown Company"))
            raw_id = "|".join([company, title, job_url])
            jobs.append(
                {
                    "job_id": f"himalayas_{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:18]}",
                    "company": company,
                    "title": self._clean_text(title),
                    "jd_text": description,
                    "discovered_url": job_url,
                    "url": job_url,
                    "source": "Web Feed: Himalayas",
                    "location": location,
                    "posted_at": (
                        item.get("publishedAt")
                        or item.get("published_at")
                        or item.get("postedAt")
                        or item.get("posted_at")
                        or item.get("createdAt")
                        or item.get("created_at")
                    ),
                    "search_query": "himalayas public feed",
                }
            )
            if len(jobs) >= max_results:
                break
        return jobs

    def _search_simplify_new_grad(self, *, max_results: int) -> list[dict[str, Any]]:
        url = "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md"
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers) as client:
                response = client.get(url)
                response.raise_for_status()
                readme = response.text
        except Exception as exc:
            logger.warning("Simplify new-grad feed failed: %s", exc)
            return []

        sections = self._new_grad_sections(readme)
        jobs: list[dict[str, Any]] = []
        for category, section in sections:
            if category not in {
                "software engineering",
                "data science, ai & machine learning",
            }:
                continue
            soup = BeautifulSoup(section, "html.parser")
            for table in soup.find_all("table"):
                last_company = ""
                for row in table.find_all("tr")[1:]:
                    cells = row.find_all("td")
                    if len(cells) < 5:
                        continue
                    row_text = row.get_text(" ", strip=True)
                    if self._new_grad_row_blocked(row_text):
                        continue

                    company = self._clean_text(self._strip_emoji(cells[0].get_text(" ", strip=True))) or last_company
                    if company:
                        last_company = company
                    title = self._clean_text(self._strip_emoji(cells[1].get_text(" ", strip=True)))
                    location = self._clean_text(self._strip_emoji(cells[2].get_text(" ", strip=True)))
                    age = self._clean_text(self._strip_emoji(cells[4].get_text(" ", strip=True)))
                    apply_url = self._new_grad_apply_url(row)
                    combined = f"{title}\n{company}\n{location}\n{category}"
                    age_hours = self._posted_age_hours(age)

                    if (
                        not apply_url
                        or not company
                        or not title
                        or (age_hours is not None and age_hours > DISCOVERY_MAX_AGE_DAYS * 24)
                        or not self._location_ok(location, combined)
                        or not self._passes_feed_title_prefilter(title)
                    ):
                        continue

                    jd_text = (
                        f"{title} at {company}. Category: {category}. "
                        f"Location: {location or 'Not listed'}. Listed in a 2026 new-grad roles feed. "
                        "Target level signal: new grad / entry level. "
                        "Open the original posting for full responsibilities and qualifications."
                    )
                    raw_id = "|".join([company, title, location, apply_url])
                    jobs.append(
                        {
                            "job_id": f"simplify_{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:18]}",
                            "company": company,
                            "title": title,
                            "jd_text": jd_text,
                            "discovered_url": apply_url,
                            "url": apply_url,
                            "source": "Web Feed: Simplify New Grad",
                            "location": location,
                            "posted_at": age,
                            "search_query": category,
                        }
                    )
                    if len(jobs) >= max_results:
                        return self._dedupe(jobs)
        return self._dedupe(jobs)[:max_results]

    def _search_themuse(self, *, max_results: int) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        page_count = 4
        params = {
            "category": "Data and Analytics",
            "location": "United States",
            "descending": "true",
        }
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers={**self.headers, "Accept": "application/json"}) as client:
                for page in range(1, page_count + 1):
                    response = client.get("https://www.themuse.com/api/public/jobs", params={**params, "page": page})
                    response.raise_for_status()
                    payload = response.json()
                    for item in payload.get("results", []):
                        title = str(item.get("name") or "").strip()
                        description = self._clean_html(str(item.get("contents") or ""))
                        locations = item.get("locations") or []
                        location = ", ".join(str(location.get("name") or "") for location in locations if location.get("name"))
                        combined = f"{title}\n{description}"
                        if (
                            not self._location_ok(location, combined)
                            or not self._passes_role_prefilter(title, description)
                            or not self._looks_like_job_text(combined)
                        ):
                            continue
                        company = self._clean_text(str((item.get("company") or {}).get("name") or "Unknown Company"))
                        refs = item.get("refs") or {}
                        job_url = str(refs.get("landing_page") or item.get("url") or "")
                        raw_id = "|".join([company, title, job_url])
                        jobs.append(
                            {
                                "job_id": f"themuse_{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:18]}",
                                "company": company,
                                "title": self._clean_text(title),
                                "jd_text": description,
                                "discovered_url": job_url,
                                "url": job_url,
                                "source": "Web Feed: The Muse",
                                "location": location or "United States",
                                "posted_at": item.get("publication_date") or item.get("date"),
                                "search_query": "themuse public feed",
                            }
                        )
                        if len(jobs) >= max_results:
                            return jobs
        except Exception as exc:
            logger.warning("The Muse job feed failed: %s", exc)
        return jobs

    def _search_remotive(self, *, max_results: int) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        for query in ["data scientist", "machine learning", "ai engineer", "data analyst", "python"]:
            url = f"https://remotive.com/api/remote-jobs?search={quote_plus(query)}"
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    payload = response.json()
            except Exception as exc:
                logger.warning("Remotive job feed failed for %r: %s", query, exc)
                continue

            for item in payload.get("jobs", []):
                title = str(item.get("title") or "").strip()
                description = self._clean_html(str(item.get("description") or ""))
                location = str(item.get("candidate_required_location") or "Remote").strip()
                combined = f"{title}\n{description}"
                if (
                    not self._location_ok(location, combined)
                    or not self._passes_role_prefilter(title, description)
                    or not self._looks_like_job_text(combined)
                ):
                    continue
                job_url = str(item.get("url") or "")
                company = str(item.get("company_name") or "Unknown Company").strip()
                raw_id = "|".join([company, title, job_url])
                jobs.append(
                    {
                        "job_id": f"remotive_{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:18]}",
                        "company": company,
                        "title": title,
                        "jd_text": description,
                        "discovered_url": job_url,
                        "url": job_url,
                        "source": "Web Feed: Remotive",
                        "location": location,
                        "posted_at": item.get("publication_date"),
                        "search_query": query,
                    }
                )
                if len(jobs) >= max_results:
                    return jobs
        return jobs

    def _search_remotejobs_org(self, *, max_results: int) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        queries = [
            ("data-science", "data scientist"),
            ("data-science", "data analyst"),
            ("data-science", "machine learning"),
            ("data-science", "ai engineer"),
            ("programming", "python data"),
            ("programming", "machine learning"),
        ]
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={**self.headers, "Accept": "application/json"},
            ) as client:
                for category, query in queries:
                    for offset in range(0, 100, 50):
                        response = client.get(
                            "https://remotejobs.org/api/v1/jobs",
                            params={"category": category, "q": query, "limit": 50, "offset": offset},
                        )
                        response.raise_for_status()
                        payload = response.json()
                        for item in payload.get("data", []):
                            title = str(item.get("title") or "").strip()
                            description = self._clean_html(str(item.get("description") or ""))
                            location = str(item.get("location") or "Remote").strip() or "Remote"
                            combined = f"{title}\n{description}"
                            if (
                                not self._location_ok(location, combined)
                                or not self._passes_role_prefilter(title, description)
                                or not self._looks_like_job_text(combined)
                            ):
                                continue
                            company_data = item.get("company") if isinstance(item.get("company"), dict) else {}
                            company = self._clean_text(str(company_data.get("name") or "Unknown Company"))
                            job_url = str(item.get("apply_url") or item.get("url") or "")
                            raw_id = "|".join([company, title, job_url])
                            jobs.append(
                                {
                                    "job_id": f"remotejobs_org_{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:18]}",
                                    "company": company,
                                    "title": self._clean_text(title),
                                    "jd_text": description,
                                    "discovered_url": job_url,
                                    "url": job_url,
                                    "source": "Web Feed: RemoteJobs.org",
                                    "location": location,
                                    "posted_at": item.get("posted_at"),
                                    "search_query": f"remotejobs.org {category} {query}",
                                    "salary_text": item.get("salary_text"),
                                    "job_type": item.get("type"),
                                }
                            )
                            if len(jobs) >= max_results:
                                return self._dedupe(jobs)
                        pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
                        if not pagination.get("has_more"):
                            break
        except Exception as exc:
            logger.warning("RemoteJobs.org job feed failed: %s", exc)
        return self._dedupe(jobs)[:max_results]

    def _search_arbeitnow(self, *, max_results: int) -> list[dict[str, Any]]:
        url = "https://www.arbeitnow.com/api/job-board-api"
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning("Arbeitnow job feed failed: %s", exc)
            return []

        jobs: list[dict[str, Any]] = []
        for item in payload.get("data", []):
            title = str(item.get("title") or "").strip()
            description = self._clean_html(str(item.get("description") or ""))
            location = str(item.get("location") or "").strip()
            combined = f"{title}\n{description}"
            if (
                not self._location_ok(location, combined)
                or not self._passes_role_prefilter(title, description)
                or not self._looks_like_job_text(combined)
            ):
                continue
            job_url = str(item.get("url") or "")
            company = str(item.get("company_name") or "Unknown Company").strip()
            raw_id = "|".join([company, title, job_url])
            jobs.append(
                {
                    "job_id": f"arbeitnow_{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:18]}",
                    "company": company,
                    "title": title,
                    "jd_text": description,
                    "discovered_url": job_url,
                    "url": job_url,
                    "source": "Web Feed: Arbeitnow",
                    "location": location,
                    "posted_at": item.get("created_at"),
                    "search_query": "arbeitnow public feed",
                }
            )
            if len(jobs) >= max_results:
                break
        return jobs

    @staticmethod
    def _new_grad_sections(readme: str) -> list[tuple[str, str]]:
        matches = list(re.finditer(r"^##\s+(.+?)\s+New Grad Roles\s*$", readme, flags=re.MULTILINE))
        sections: list[tuple[str, str]] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(readme)
            category = re.sub(r"[^\w\s,&+-]", "", match.group(1)).strip().lower()
            sections.append((category, readme[start:end]))
        return sections

    @staticmethod
    def _new_grad_row_blocked(text: str) -> bool:
        lowered = text.lower()
        return any(
            blocked in text or blocked.lower() in lowered
            for blocked in [
                "🔒",
                "🇺🇸",
                "🛂",
                "requires u.s. citizenship",
                "u.s. citizenship required",
                "us citizenship required",
                "does not offer sponsorship",
                "no sponsorship",
                "will not sponsor",
            ]
        )

    @staticmethod
    def _new_grad_apply_url(row: Any) -> str:
        for link in row.find_all("a"):
            href = str(link.get("href") or "")
            if not href.startswith("http"):
                continue
            parsed = urlparse(href)
            host = parsed.netloc.lower()
            path = parsed.path.lower()
            if host.endswith("simplify.jobs") and (path.startswith("/c/") or path.startswith("/p/")):
                continue
            if "imgur.com" in host:
                continue
            return href
        for link in row.find_all("a"):
            href = str(link.get("href") or "")
            if href.startswith("http"):
                return href
        return ""

    @staticmethod
    def _strip_emoji(value: str) -> str:
        return re.sub(r"[\U00010000-\U0010ffff]", "", value)

    def _search_duckduckgo(self, query: str, *, limit: int) -> list[dict[str, str]]:
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers) as client:
                response = client.get(url)
                response.raise_for_status()
        except Exception as exc:
            logger.warning("Web job search failed for %r: %s", query, exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results: list[dict[str, str]] = []
        for node in soup.select(".result"):
            link = node.select_one("a.result__a") or node.select_one("a[href]")
            if not link:
                continue
            href = self._resolve_duckduckgo_url(str(link.get("href") or ""))
            title = link.get_text(" ", strip=True)
            snippet_node = node.select_one(".result__snippet")
            snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
            if href and title:
                results.append({"title": unescape(title), "url": href, "snippet": unescape(snippet), "query": query})
            if len(results) >= limit:
                break
        return results

    def _search_bing(self, query: str, *, limit: int) -> list[dict[str, str]]:
        url = f"https://www.bing.com/search?q={quote_plus(query)}"
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers) as client:
                response = client.get(url)
                response.raise_for_status()
        except Exception as exc:
            logger.warning("Fallback Bing job search failed for %r: %s", query, exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results: list[dict[str, str]] = []
        for node in soup.select("li.b_algo"):
            link = node.select_one("h2 a[href]") or node.select_one("a[href]")
            if not link:
                continue
            href = str(link.get("href") or "")
            title = link.get_text(" ", strip=True)
            snippet_node = node.select_one(".b_caption p") or node.select_one("p")
            snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
            if href and title:
                results.append({"title": unescape(title), "url": href, "snippet": unescape(snippet), "query": query})
            if len(results) >= limit:
                break
        return results

    def _result_to_job(self, result: dict[str, str]) -> dict[str, Any] | None:
        url = self._normalize_url(result["url"])
        if not url:
            return None

        page_text = self._fetch_page_text(url)
        combined = f"{result.get('title', '')}\n{result.get('snippet', '')}\n{page_text}"
        if (
            self._looks_like_listing_page(result.get("title", ""), url, combined)
            or not self._passes_role_prefilter(result.get("title", ""), combined)
            or not self._looks_like_job_text(combined)
        ):
            return None

        title = self._infer_title(result.get("title", ""), result.get("snippet", ""))
        company = self._infer_company(result.get("title", ""), url)
        location = self._infer_location(combined)
        if not self._location_ok(location, combined):
            return None
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        raw_id = "|".join([company, title, url])
        return {
            "job_id": f"web_{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:18]}",
            "company": company,
            "title": title,
            "jd_text": page_text or result.get("snippet", ""),
            "discovered_url": url,
            "url": url,
            "source": f"Web Search: {domain}",
            "location": location,
            "search_query": result.get("query", ""),
            "search_snippet": result.get("snippet", ""),
        }

    def _fetch_page_text(self, url: str) -> str:
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers) as client:
                response = client.get(url)
                response.raise_for_status()
        except Exception:
            return ""

        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            return ""
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            node.decompose()
        preferred: list[str] = []
        for selector in [
            "main",
            "article",
            "[data-automation-id*='job']",
            "[class*='job']",
            "[id*='job']",
            ".content",
            "section",
        ]:
            for node in soup.select(selector):
                text = node.get_text("\n", strip=True)
                if len(text) > 350:
                    preferred.append(text)
            if preferred:
                break
        text = "\n\n".join(preferred) if preferred else soup.get_text("\n", strip=True)
        return re.sub(r"\n{3,}", "\n\n", text).strip()[:14000]

    @staticmethod
    def _clean_html(value: str) -> str:
        soup = BeautifulSoup(value, "html.parser")
        return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True)).strip()[:14000]

    @staticmethod
    def _clean_text(value: str) -> str:
        return unescape(re.sub(r"\s+", " ", value).strip())

    @staticmethod
    def _queries() -> list[str]:
        return [
            '"junior data scientist" "United States" "apply" job',
            '"entry level data scientist" "United States" "apply" job',
            '"machine learning engineer" "new grad" "United States" job',
            '"junior machine learning engineer" Python "apply" job',
            '"AI engineer" "entry level" Python job',
            '"data analyst" "junior" SQL Python "United States" job',
            '"data engineer" "entry level" SQL Python "United States" job',
            '"business analyst" "data" SQL Python "United States" job',
            '"computer vision engineer" "entry level" Python job',
            'site:jobs.ashbyhq.com ("Data Scientist" OR "Machine Learning Engineer") "United States"',
            'site:boards.greenhouse.io ("Data Scientist" OR "Machine Learning Engineer") "United States"',
            'site:jobs.lever.co ("Data Scientist" OR "Machine Learning Engineer") "United States"',
            'site:myworkdayjobs.com "Data Scientist" "United States" "Apply"',
        ]

    @staticmethod
    def _sponsor_queries(company: str) -> list[str]:
        company = WebJobSearchService._sponsor_search_name(company)
        return [
            f'"{company}" ("data scientist" OR "machine learning engineer" OR "data analyst" OR "data engineer" OR "AI engineer") ("0-2 years" OR "0 to 2 years" OR "new grad" OR "entry level" OR "junior") careers',
        ]

    @staticmethod
    def _sponsor_search_name(company: str) -> str:
        cleaned = re.sub(
            r"\b(?:inc|incorporated|llc|ltd|corp|corporation|company|co|national association|services|advisory services)\b\.?",
            "",
            company,
            flags=re.IGNORECASE,
        )
        cleaned = cleaned.replace("&", " ")
        return re.sub(r"\s+", " ", cleaned).strip(" ,.-") or company

    @staticmethod
    def _resolve_duckduckgo_url(href: str) -> str:
        if href.startswith("//"):
            href = f"https:{href}"
        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            values = parse_qs(parsed.query).get("uddg")
            if values:
                return values[0]
        return href

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        return parsed._replace(fragment="").geturl()

    @staticmethod
    def _looks_like_job_url(url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        if WebJobSearchService._is_blocked_source_url(url):
            return False
        if any(blocked in host for blocked in ["google.", "duckduckgo.", "bing.", "yahoo.", "facebook.", "x.com"]):
            return False
        if any(path.endswith(ext) for ext in [".pdf", ".jpg", ".png", ".zip"]):
            return False
        if any(blocked in path for blocked in ["/article", "/blog", "/guide", "best-platform", "salary", "course"]):
            return False
        signals = ["job", "career", "position", "opening", "apply", "requisition", "posting", "candidate"]
        return any(signal in f"{host} {path}" for signal in signals)

    @classmethod
    def _within_posted_age(cls, job: dict[str, Any], *, max_age_days: int) -> bool:
        age_hours = cls._posted_age_hours(cls._posted_value(job))
        return age_hours is None or age_hours <= max_age_days * 24

    @staticmethod
    def _looks_like_listing_page(title: str, url: str, text: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        host = parsed.netloc.lower()
        lowered_title = title.lower()
        lowered = f"{lowered_title}\n{text[:3000].lower()}"

        collection_phrases = [
            "job listings",
            "search results",
            "browse jobs",
            "find jobs",
            "open jobs",
            "available jobs",
            "jobs in ",
            "remote jobs",
            "recommended jobs",
            "top jobs",
            "explore jobs",
        ]
        if any(phrase in lowered_title for phrase in collection_phrases):
            return True
        if re.search(
            r"\b\d{2,5}\s+(?:remote\s+)?(?:junior\s+|entry\s+level\s+)?"
            r"(?:data scientist|data analyst|data engineer|machine learning engineer|ai engineer|software engineer)\b",
            lowered,
        ):
            return True
        if any(part in path for part in ["/search", "/job-search", "/jobs/search", "/careers/search"]):
            return True
        if any(host.endswith(domain) for domain in ["remoterocketship.com", "levels.fyi", "builtin.com"]) and re.search(
            r"\b\d{2,5}\s+.+\bjobs?\b",
            lowered_title,
        ):
            return True
        return False

    @staticmethod
    def _is_blocked_source_url(url: str) -> bool:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        return any(host == domain or host.endswith(f".{domain}") for domain in BLOCKED_DISCOVERY_DOMAINS)

    @staticmethod
    def _looks_like_job_text(text: str) -> bool:
        lowered = text.lower()
        job_signals = ["responsibilities", "requirements", "qualifications", "apply", "job", "role", "position"]
        target_signals = [
            "data scientist",
            "machine learning",
            "ai engineer",
            "data analyst",
            "data engineer",
            "business analyst",
            "computer vision",
            "python",
            "sql",
            "analytics",
        ]
        return any(signal in lowered for signal in job_signals) and any(signal in lowered for signal in target_signals)

    @staticmethod
    def _has_explicit_early_career_signal(text: str) -> bool:
        lowered = text.lower()
        if any(term in lowered for term in ["new grad", "new graduate", "entry level", "early career", "university grad", "junior"]):
            return True
        range_matches = re.finditer(
            r"\b0\s*(?:-|to|through|/)\s*(\d+(?:\.\d+)?)\s*(?:years|year|yrs|yr)\b",
            lowered,
        )
        return any(float(match.group(1)) <= 2 for match in range_matches)

    @staticmethod
    def _passes_role_prefilter(title: str, text: str) -> bool:
        title_text = title.lower()
        combined = f"{title}\n{text}".lower()
        senior_terms = [
            "senior",
            "sr.",
            "staff",
            "principal",
            "lead ",
            "manager",
            "director",
            "architect",
            "head of",
            "vp ",
        ]
        if any(term in title_text for term in senior_terms):
            return False

        direct_title_terms = [
            "data scientist",
            "data engineer",
            "data analyst",
            "business analyst",
            "machine learning engineer",
            "ml engineer",
            "ai engineer",
            "artificial intelligence engineer",
            "computer vision engineer",
            "analytics engineer",
        ]
        if any(term in title_text for term in direct_title_terms):
            return True

        if "analyst" in title_text and any(
            term in combined
            for term in [
                "data analysis",
                "analytics",
                "sql",
                "python",
                "machine learning",
                "business intelligence",
            ]
        ):
            return True

        if ("software engineer" in title_text or "python developer" in title_text or "developer" in title_text) and any(
            term in combined
            for term in [
                "python",
                "machine learning",
                "large language model",
                "llm",
                "artificial intelligence",
                "data pipeline",
                "analytics",
            ]
        ):
            return True

        return any(
            term in combined[:1800]
            for term in [
                "entry level data scientist",
                "junior data scientist",
                "new grad machine learning",
                "junior machine learning",
                "entry level data analyst",
            ]
        )

    @staticmethod
    def _passes_feed_title_prefilter(title: str) -> bool:
        title_text = title.lower()
        if any(term in title_text for term in ["senior", "staff", "principal", "lead ", "manager", "director", "architect"]):
            return False

        direct_title_terms = [
            "data scientist",
            "data engineer",
            "data analyst",
            "business analyst",
            "machine learning engineer",
            "ml engineer",
            "ai engineer",
            "artificial intelligence engineer",
            "computer vision engineer",
            "analytics engineer",
            "applied scientist",
            "decision scientist",
            "llm engineer",
            "generative ai engineer",
        ]
        if any(term in title_text for term in direct_title_terms):
            return True

        if "analyst" in title_text:
            return any(term in title_text for term in ["data", "business", "analytics", "reporting", "operations", "product", "bi "])

        if "software engineer" in title_text or "developer" in title_text:
            return any(term in title_text for term in ["ai", "ml", "machine learning", "python", "data", "computer vision"])

        return False

    @staticmethod
    def _with_sponsor_metadata(job: dict[str, Any], sponsor: dict[str, Any]) -> dict[str, Any]:
        updated = dict(job)
        updated["company"] = sponsor.get("employer_name") or updated.get("company")
        updated["source"] = "Sponsor-backed Web Search: DOL OFLC LCA"
        updated["is_h1b_sponsor"] = True
        updated["h1b_sponsor_employer"] = sponsor.get("employer_name")
        updated["h1b_certified_lca_count"] = sponsor.get("certified_lca_count")
        updated["h1b_relevant_lca_count"] = sponsor.get("relevant_lca_count")
        updated["h1b_entry_level_lca_count"] = sponsor.get("entry_level_lca_count")
        updated["h1b_source_url"] = sponsor.get("source_url")
        updated["h1b_fiscal_year"] = sponsor.get("fiscal_year")
        updated["h1b_quarter"] = sponsor.get("quarter")
        updated["source_scope"] = "sponsor_backed_entry_search"
        return updated

    @staticmethod
    def _infer_title(title: str, snippet: str) -> str:
        cleaned = re.sub(r"\s+", " ", title).strip(" -|")
        cleaned = re.sub(r"\b(apply|careers?|jobs?|job details?|job posting)\b", "", cleaned, flags=re.IGNORECASE).strip(" -|")
        for separator in [" at ", " | ", " - ", " — ", " – "]:
            if separator in cleaned:
                parts = [part.strip() for part in cleaned.split(separator) if part.strip()]
                if parts:
                    cleaned = parts[0]
                    break
        if len(cleaned) < 8:
            cleaned = snippet[:100].strip(" -|")
        return cleaned[:180] or "Untitled Job"

    @staticmethod
    def _infer_company(title: str, url: str) -> str:
        for pattern in [r"\bat\s+([^|-]+)", r"\|\s*([^|]+)$", r"-\s*([^-]+)$"]:
            match = re.search(pattern, title, flags=re.IGNORECASE)
            if match:
                company = match.group(1).strip(" -|")
                if company and len(company) <= 80:
                    return company
        host = urlparse(url).netloc.lower().removeprefix("www.")
        host = re.sub(r"\b(jobs|careers|boards|job-boards)\.", "", host)
        base = host.split(".")[0].replace("-", " ").replace("_", " ")
        return base.title()[:80] or "Unknown Company"

    @staticmethod
    def _infer_location(text: str) -> str:
        patterns = [
            r"\bRemote(?:,\s*United States|\s*-\s*United States)?\b",
            r"\b(?:New York|San Francisco|Santa Monica|Seattle|Austin|Boston|Chicago|Dallas|Arlington|Atlanta|Los Angeles|Washington),?\s+(?:CA|NY|TX|WA|MA|IL|GA|VA|DC)\b",
            r"\bUnited States\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(0)
        return ""

    @staticmethod
    def _location_ok(location: str, text: str) -> bool:
        location_text = location.lower()
        combined = f"{location}\n{text[:1500]}".lower()
        explicit_us = [
            "united states",
            "usa",
            "u.s.",
            "us only",
            "remote in usa",
            "remote, united states",
            "remote - united states",
            "san francisco",
            "new york",
            "seattle",
            "austin",
            "boston",
            "chicago",
            "dallas",
            "arlington",
            "atlanta",
            "los angeles",
            "california",
            "texas",
        ]
        remote_terms = ["remote", "virtual", "worldwide", "anywhere"]
        negative = [
            "germany",
            "deutschland",
            "berlin",
            "munich",
            "stuttgart",
            "europe only",
            "eu only",
            "united kingdom",
            "london",
            "canada only",
            "canada",
            "toronto",
            "ottawa",
            "edson",
            "norway",
            "oslo",
            "latvia",
            "riga",
            "india",
            "spain",
            "france",
            "italy",
            "romania",
            "brazil",
            "mexico",
            "argentina",
            "uruguay",
            "netherlands",
            "costa rica",
        ]

        if location_text:
            if any(term in location_text for term in negative):
                return False
            if any(term in location_text for term in explicit_us):
                return True
            if any(term in location_text for term in remote_terms):
                if any(term in combined for term in negative):
                    return False
                return any(term in combined for term in explicit_us)
            return False

        if any(term in combined for term in explicit_us):
            return True
        return not any(term in combined for term in negative)

    @classmethod
    def posted_age_hours(cls, value: Any, *, now: datetime | None = None) -> float | None:
        return cls._posted_age_hours(value, now=now)

    @staticmethod
    def _posted_value(job: dict[str, Any]) -> Any:
        for key in (
            "posted_at",
            "published_at",
            "publishedAt",
            "publication_date",
            "created_at",
            "createdAt",
            "date",
            "epoch",
        ):
            if job.get(key):
                return job.get(key)
        return None

    @classmethod
    def _posted_age_hours(cls, value: Any, *, now: datetime | None = None) -> float | None:
        if value is None:
            return None

        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        else:
            now = now.astimezone(UTC)

        if isinstance(value, (int, float)):
            return cls._timestamp_age_hours(float(value), now=now)

        text = str(value).strip()
        if not text:
            return None

        lowered = text.lower()
        if lowered in {"now", "new", "today", "just now"}:
            return 0.0
        if "yesterday" in lowered:
            return 24.0

        for pattern, multiplier in [
            (r"(\d+(?:\.\d+)?)\s*(?:m|min|mins|minute|minutes)\b", 1 / 60),
            (r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b", 1),
            (r"(\d+(?:\.\d+)?)\s*(?:d|day|days)\b", 24),
            (r"(\d+(?:\.\d+)?)\s*(?:w|week|weeks)\b", 24 * 7),
            (r"(\d+(?:\.\d+)?)\s*(?:mo|mos|month|months)\b", 24 * 30),
            (r"(\d+(?:\.\d+)?)\s*(?:y|yr|yrs|year|years)\b", 24 * 365),
        ]:
            match = re.search(pattern, lowered)
            if match:
                return float(match.group(1)) * multiplier

        if re.fullmatch(r"\d{10,13}", text):
            return cls._timestamp_age_hours(float(text), now=now)

        parsed_dt = cls._parse_datetime(text)
        if parsed_dt is None:
            return None
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=UTC)
        else:
            parsed_dt = parsed_dt.astimezone(UTC)
        return max(0.0, (now - parsed_dt).total_seconds() / 3600)

    @staticmethod
    def _timestamp_age_hours(value: float, *, now: datetime) -> float | None:
        try:
            timestamp = value / 1000 if value > 10_000_000_000 else value
            posted_at = datetime.fromtimestamp(timestamp, tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None
        return max(0.0, (now - posted_at).total_seconds() / 3600)

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass

        month_day = WebJobSearchService._parse_month_day(value)
        if month_day is not None:
            return month_day

        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None

    @staticmethod
    def _parse_month_day(value: str, *, now: datetime | None = None) -> datetime | None:
        match = re.fullmatch(
            r"\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s*",
            value,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        now = now or datetime.now(UTC)
        month_lookup = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        month = month_lookup[match.group(1).lower()]
        day = int(match.group(2))
        try:
            parsed = datetime(now.year, month, day, tzinfo=UTC)
        except ValueError:
            return None
        if parsed > now:
            parsed = datetime(now.year - 1, month, day, tzinfo=UTC)
        return parsed

    @staticmethod
    def _freshness_label(hours: float) -> str:
        if hours < 1:
            return "<1h"
        if hours < 24:
            return f"{round(hours)}h"
        return f"{round(hours / 24)}d"

    @staticmethod
    def _dedupe(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for job in jobs:
            key = str(job.get("discovered_url") or job.get("url") or job.get("job_id") or "").strip().lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(job)
        return deduped
