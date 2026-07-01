from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from app.scrapers.ats.ashby_scraper import AshbyScraper
from app.scrapers.ats.greenhouse_scraper import GreenhouseScraper
from app.scrapers.ats.lever_scraper import LeverScraper
from app.schemas.job import JobQualityGateRequest
from app.services.h1b_sponsor_service import H1BSponsorService
from app.services.job_quality_gate_service import JobQualityGateService
from app.services.web_job_search_service import WebJobSearchService

logger = logging.getLogger(__name__)


INACTIVE_SOURCE_TERMS = ("jobright",)
RECOMMENDED_MAX_AGE_DAYS = 21


class JobFeedService:
    """Loads real job leads for the recommendation UI without sending anything to n8n."""

    def __init__(
        self,
        *,
        quality_gate: JobQualityGateService,
        targets_path: str = "data/target_companies.json",
        cache_path: str = "data/cache/job_feed/latest_jobs.json",
        recent_cache_path: str = "data/cache/job_feed/recent_24h_jobs.json",
    ) -> None:
        self.quality_gate = quality_gate
        self.targets_path = Path(targets_path)
        self.cache_path = Path(cache_path)
        self.recent_cache_path = Path(recent_cache_path)
        self.ashby = AshbyScraper()
        self.greenhouse = GreenhouseScraper()
        self.lever = LeverScraper()
        self.web = WebJobSearchService()
        self.h1b_sponsors = H1BSponsorService()

    def load_cached_jobs(self, limit: int = 100) -> list[dict]:
        payload = self._load_cache_payload()
        jobs = payload.get("jobs", [])
        return self._active_source_jobs(jobs)[:limit] if isinstance(jobs, list) else []

    def load_cached_scraped_jobs(self, limit: int = 200) -> list[dict]:
        payload = self._load_cache_payload()
        jobs = payload.get("all_jobs") or payload.get("jobs", [])
        return self._active_source_jobs(jobs)[:limit] if isinstance(jobs, list) else []

    def load_cached_recent_jobs(self, limit: int = 100) -> list[dict]:
        payload = self._load_recent_cache_payload()
        jobs = payload.get("jobs", [])
        return self._active_source_jobs(jobs)[:limit] if isinstance(jobs, list) else []

    def load_recent_payload(self) -> dict:
        return self._load_recent_cache_payload()

    def refresh_live_jobs(
        self,
        *,
        max_companies: int = 8,
        max_jobs_per_company: int = 8,
        include_rejected: bool = False,
        include_web: bool = False,
        web_max_results: int = 20,
        include_sponsors: bool = False,
        sponsor_max_companies: int = 25,
        sponsor_max_results: int = 30,
    ) -> dict:
        previous_payload = self._load_cache_payload()
        targets = self._load_targets()[:max_companies]
        sponsors: list[dict] = []
        sponsor_load_error = ""
        if include_sponsors:
            try:
                sponsors = self.h1b_sponsors.load_sponsors(limit=sponsor_max_companies)
            except Exception as exc:
                sponsor_load_error = str(exc)
                logger.warning("Could not load DOL H1B sponsor cache: %s", exc)
        sponsor_lookup = self._sponsor_lookup(sponsors)
        jobs: list[dict] = []
        all_jobs: list[dict] = []
        target_rows: list[dict] = []

        for target in targets:
            company = target.get("company", "")
            ats_type = target.get("ats_type", "")
            row = {
                "company": company,
                "ats_type": ats_type,
                "status": "started",
                "scraped": 0,
                "kept": 0,
                "error": "",
            }
            try:
                scraped = self._scrape_target(target, max_jobs=max_jobs_per_company)
                row["scraped"] = len(scraped)
                for job in scraped:
                    job = self._mark_current_source_active(job, ats_type=ats_type)
                    job = self._with_dol_sponsor_signal(job, sponsor_lookup)
                    enriched = self.ensure_jd_text(job)
                    all_jobs.append(enriched)
                    if include_rejected or enriched.get("quality_actionable"):
                        jobs.append(enriched)
                        row["kept"] += 1
                row["status"] = "ok"
            except Exception as exc:
                logger.warning("Job feed scrape failed for %s: %s", company, exc)
                row["status"] = "failed"
                row["error"] = str(exc)
            target_rows.append(row)

        if include_web:
            row = {
                "company": "Broad Web Search",
                "ats_type": "web",
                "status": "started",
                "scraped": 0,
                "kept": 0,
                "error": "",
            }
            try:
                scraped = self.web.search_jobs(max_results=web_max_results)
                row["scraped"] = len(scraped)
                for job in scraped:
                    job = self._with_dol_sponsor_signal(job, sponsor_lookup)
                    enriched = self.ensure_jd_text(job)
                    all_jobs.append(enriched)
                    if include_rejected or enriched.get("quality_actionable"):
                        jobs.append(enriched)
                        row["kept"] += 1
                row["status"] = "ok"
            except Exception as exc:
                logger.warning("Broad web job search failed: %s", exc)
                row["status"] = "failed"
                row["error"] = str(exc)
            target_rows.append(row)

        if include_sponsors:
            row = {
                "company": "DOL H1B Sponsor Search",
                "ats_type": "sponsor_web",
                "status": "started",
                "scraped": 0,
                "kept": 0,
                "error": "",
            }
            try:
                if sponsor_load_error:
                    raise RuntimeError(sponsor_load_error)
                scraped = self.web.search_sponsored_entry_jobs(
                    sponsors,
                    max_results=sponsor_max_results,
                )
                row["sponsor_count"] = len(sponsors)
                row["scraped"] = len(scraped)
                for job in scraped:
                    job = self._with_dol_sponsor_signal(job, sponsor_lookup)
                    enriched = self.ensure_jd_text(job)
                    all_jobs.append(enriched)
                    if include_rejected or enriched.get("quality_actionable"):
                        jobs.append(enriched)
                        row["kept"] += 1
                row["status"] = "ok"
            except Exception as exc:
                logger.warning("DOL sponsor-backed job search failed: %s", exc)
                row["status"] = "failed"
                row["error"] = str(exc)
            target_rows.append(row)

        fresh_jobs = self._dedupe_jobs(jobs)
        fresh_all_jobs = self._dedupe_jobs(all_jobs)
        previous_jobs = self._recommendation_cache_jobs(
            self._active_source_jobs(previous_payload.get("jobs", [])),
            include_rejected=include_rejected,
            max_age_days=RECOMMENDED_MAX_AGE_DAYS,
        )
        previous_all_jobs = self._recommendation_cache_jobs(
            self._active_source_jobs(previous_payload.get("all_jobs") or previous_jobs),
            include_rejected=True,
            max_age_days=RECOMMENDED_MAX_AGE_DAYS,
        )
        merged_jobs = self._merge_fresh_with_cached(fresh_jobs, previous_jobs, limit=250)
        merged_all_jobs = self._merge_fresh_with_cached(fresh_all_jobs, previous_all_jobs, limit=500)

        payload = {
            "created_at": datetime.now(UTC).isoformat(),
            "targets": target_rows,
            "fresh_job_count": len(fresh_jobs),
            "fresh_all_job_count": len(fresh_all_jobs),
            "preserved_job_count": max(0, len(merged_jobs) - len(fresh_jobs)),
            "preserved_all_job_count": max(0, len(merged_all_jobs) - len(fresh_all_jobs)),
            "jobs": merged_jobs,
            "all_jobs": merged_all_jobs,
        }
        return self.persist_payload(payload)

    def refresh_recent_jobs(
        self,
        *,
        hours: int = 24,
        max_results: int = 30,
        include_rejected: bool = False,
        max_target_companies: int = 8,
        include_targets: bool = True,
    ) -> dict:
        previous_payload = self._load_recent_cache_payload()
        all_jobs: list[dict] = []
        jobs: list[dict] = []
        target_rows: list[dict] = [
            {
                "company": f"Fresh {hours}h Public Feeds",
                "ats_type": "web_recent",
                "status": "started",
                "scraped": 0,
                "kept": 0,
                "error": "",
            }
        ]

        try:
            scraped = self.web.search_recent_jobs(max_results=max_results, hours=hours)
            target_rows[0]["scraped"] = len(scraped)
            for job in scraped:
                enriched = self.ensure_jd_text(job)
                all_jobs.append(enriched)
                if include_rejected or enriched.get("quality_actionable"):
                    jobs.append(enriched)
                    target_rows[0]["kept"] += 1
            target_rows[0]["status"] = "ok"
        except Exception as exc:
            logger.warning("Fresh web job search failed: %s", exc)
            target_rows[0]["status"] = "failed"
            target_rows[0]["error"] = str(exc)

        if include_targets:
            for target in self._load_targets()[:max_target_companies]:
                row = {
                    "company": target.get("company", ""),
                    "ats_type": f"{target.get('ats_type', '')}_recent",
                    "status": "started",
                    "scraped": 0,
                    "kept": 0,
                    "error": "",
                }
                try:
                    scraped = self._scrape_recent_target(target, hours=hours, max_jobs=max_results)
                    row["scraped"] = len(scraped)
                    for job in scraped:
                        job = self._mark_current_source_active(job, ats_type=str(target.get("ats_type") or ""))
                        enriched = self.ensure_jd_text(job)
                        all_jobs.append(enriched)
                        if include_rejected or enriched.get("quality_actionable"):
                            jobs.append(enriched)
                            row["kept"] += 1
                    row["status"] = "ok"
                except Exception as exc:
                    logger.warning("Fresh target scrape failed for %s: %s", target.get("company", ""), exc)
                    row["status"] = "failed"
                    row["error"] = str(exc)
                target_rows.append(row)

        now = datetime.now(UTC)
        fresh_jobs = self._dedupe_jobs(jobs)
        fresh_all_jobs = self._dedupe_jobs(all_jobs)
        previous_jobs = self._recent_cached_jobs(
            self._active_source_jobs(previous_payload.get("jobs", [])),
            hours=hours,
            now=now,
            include_rejected=include_rejected,
        )
        previous_all_jobs = self._recent_cached_jobs(
            self._active_source_jobs(previous_payload.get("all_jobs") or previous_jobs),
            hours=hours,
            now=now,
            include_rejected=True,
        )
        merged_jobs = self._merge_fresh_with_cached(fresh_jobs, previous_jobs, limit=250)
        merged_all_jobs = self._merge_fresh_with_cached(fresh_all_jobs, previous_all_jobs, limit=500)

        payload = {
            "created_at": now.isoformat(),
            "window_hours": hours,
            "targets": target_rows,
            "fresh_job_count": len(fresh_jobs),
            "fresh_all_job_count": len(fresh_all_jobs),
            "preserved_job_count": max(0, len(merged_jobs) - len(fresh_jobs)),
            "preserved_all_job_count": max(0, len(merged_all_jobs) - len(fresh_all_jobs)),
            "jobs": merged_jobs,
            "all_jobs": merged_all_jobs,
        }
        return self.persist_recent_payload(payload)

    def persist_payload(self, payload: dict) -> dict:
        return self._persist_payload_to(payload, self.cache_path)

    def persist_recent_payload(self, payload: dict) -> dict:
        return self._persist_payload_to(payload, self.recent_cache_path)

    def ensure_jd_text(self, job: dict) -> dict:
        if self._needs_live_jd_text(job):
            verified = self._verify_job_availability(job)
            if self._is_availability_reject(verified):
                return verified
            job = verified

        if job.get("jd_text") and not self._needs_live_jd_text(job):
            return self._enrich_job(job)

        url = job.get("discovered_url") or job.get("url") or ""
        if not url:
            enriched = self._enrich_job(job)
            if self._needs_live_jd_text(job):
                self._apply_unverified_posting_blocker(enriched)
            return enriched

        jd_text = self.fetch_job_description(url)
        if not jd_text:
            enriched = self._enrich_job(job)
            if self._needs_live_jd_text(job):
                self._apply_unverified_posting_blocker(enriched)
            return enriched

        updated = dict(job)
        updated["jd_text"] = jd_text
        updated["jd_text_source"] = "live_posting"
        updated = self._drop_ai_fields(updated)
        return self._enrich_job(updated)

    def fetch_job_description(self, url: str) -> str:
        if not url:
            return ""

        try:
            parsed = urlparse(url)
            if parsed.netloc.lower().endswith("greenhouse.io"):
                status, _reason = self._greenhouse_job_availability(parsed)
                if status == "inactive":
                    return ""
                return self.greenhouse._safe_fetch_job_description(url)

            with httpx.Client(
                timeout=25.0,
                follow_redirects=True,
                headers={"User-Agent": "CareerSiteAgent/1.0"},
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                if self._response_looks_inactive(response):
                    return ""
                return self._extract_text(response.text)
        except Exception as exc:
            logger.warning("Could not fetch JD text from %s: %s", url, exc)
            return ""

    def _scrape_target(self, target: dict, *, max_jobs: int) -> list[dict]:
        company = target.get("company", "")
        ats_type = target.get("ats_type", "")
        board_url = target.get("url", "")

        if ats_type == "greenhouse":
            return self.greenhouse.scrape_jobs(
                company=company,
                board_url=board_url,
                source="Greenhouse Live Feed",
                max_jobs=self._expanded_board_limit(max_jobs),
                filter_relevant=True,
            )

        if ats_type == "lever":
            lever_slug = target.get("lever_slug") or board_url.split("jobs.lever.co/")[-1].split("/")[0]
            return self.lever.scrape_jobs(
                company=company,
                lever_slug=lever_slug,
                source="Lever Live Feed",
                max_jobs=max_jobs,
            )

        if ats_type == "ashby":
            ashby_slug = target.get("ashby_slug") or board_url.rstrip("/").split("/")[-1]
            return self.ashby.scrape_jobs(
                company=company,
                ashby_slug=ashby_slug,
                source="Ashby Live Feed",
                max_jobs=self._expanded_board_limit(max_jobs),
                filter_relevant=True,
            )

        return []

    @staticmethod
    def _expanded_board_limit(max_jobs: int) -> int:
        return min(max(max_jobs * 6, 80), 150)

    def _scrape_recent_target(self, target: dict, *, hours: int, max_jobs: int) -> list[dict]:
        ats_type = target.get("ats_type", "")
        if ats_type == "greenhouse":
            return self._scrape_recent_greenhouse_target(target, hours=hours, max_jobs=max_jobs)
        if ats_type == "lever":
            scraped = self._scrape_target(target, max_jobs=max_jobs)
            return self._filter_recent_source_jobs(scraped, hours=hours)[:max_jobs]
        if ats_type == "ashby":
            scraped = self._scrape_target(target, max_jobs=max_jobs)
            return self._filter_recent_source_jobs(scraped, hours=hours)[:max_jobs]
        return []

    def _scrape_recent_greenhouse_target(self, target: dict, *, hours: int, max_jobs: int) -> list[dict]:
        board_token = self._greenhouse_board_token(str(target.get("url") or ""))
        if not board_token:
            return []

        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        with httpx.Client(
            timeout=25.0,
            follow_redirects=True,
            headers={"User-Agent": "CareerSiteAgent/1.0", "Accept": "application/json"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()

        jobs: list[dict] = []
        now = datetime.now(UTC)
        for item in payload.get("jobs", []):
            posted_at = item.get("first_published") or item.get("updated_at")
            age_hours = self.web.posted_age_hours(posted_at, now=now)
            if age_hours is None or age_hours > hours:
                continue

            title = self._clean_text(str(item.get("title") or ""))
            jd_text = self._greenhouse_content_text(str(item.get("content") or ""))
            location = self._greenhouse_location_name(item)
            combined = f"{title}\n{jd_text}\n{location}"
            if (
                not title
                or not self.web._passes_role_prefilter(title, combined)
                or not self.web._looks_like_job_text(combined)
                or not self.web._location_ok(location, combined)
            ):
                continue

            company = self._clean_text(str(item.get("company_name") or target.get("company") or "Unknown Company"))
            job_url = str(item.get("absolute_url") or "")
            raw_id = "|".join([company, title, job_url])
            jobs.append(
                {
                    "job_id": f"greenhouse_recent_{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:18]}",
                    "company": company,
                    "title": title,
                    "jd_text": jd_text,
                    "discovered_url": job_url,
                    "url": job_url,
                    "source": "Greenhouse Fresh Feed",
                    "location": location,
                    "posted_at": posted_at,
                    "updated_at": item.get("updated_at"),
                    "freshness_hours": round(age_hours, 2),
                    "freshness_label": WebJobSearchService._freshness_label(age_hours),
                    "freshness_window_hours": hours,
                    "freshness_checked_at": now.isoformat(),
                    "source_scope": f"fresh_{hours}h_target",
                }
            )
            if len(jobs) >= max_jobs:
                break
        return jobs

    def _filter_recent_source_jobs(self, jobs: list[dict], *, hours: int) -> list[dict]:
        now = datetime.now(UTC)
        recent_jobs: list[dict] = []
        for job in jobs:
            age_hours = self.web.posted_age_hours(self._job_posted_value(job), now=now)
            if age_hours is None or age_hours > hours:
                continue
            updated = dict(job)
            updated["freshness_hours"] = round(age_hours, 2)
            updated["freshness_label"] = WebJobSearchService._freshness_label(age_hours)
            updated["freshness_window_hours"] = hours
            updated["freshness_checked_at"] = now.isoformat()
            updated["source_scope"] = f"fresh_{hours}h_target"
            recent_jobs.append(updated)
        return recent_jobs

    @staticmethod
    def _greenhouse_board_token(board_url: str) -> str:
        parsed = urlparse(board_url)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        return parts[0] if parts else ""

    @staticmethod
    def _greenhouse_location_name(item: dict) -> str:
        location = item.get("location") or {}
        if isinstance(location, dict):
            return str(location.get("name") or "")
        return str(location or "")

    @staticmethod
    def _greenhouse_content_text(value: str) -> str:
        return JobFeedService._extract_text(unescape(value))

    @staticmethod
    def _clean_text(value: str) -> str:
        return unescape(re.sub(r"\s+", " ", value).strip())

    @staticmethod
    def _needs_live_jd_text(job: dict) -> bool:
        if job.get("jd_text_source") == "live_posting":
            return False
        source = str(job.get("source") or "").lower()
        text = str(job.get("jd_text") or "").lower()
        if "simplify new grad" in source:
            return True
        return any(
            marker in text
            for marker in [
                "open the original posting for full responsibilities",
                "listed in a 2026 new-grad roles feed",
            ]
        )

    def _enrich_job(self, job: dict) -> dict:
        gate = self.quality_gate.evaluate(
            JobQualityGateRequest(
                company=job.get("company", ""),
                title=job.get("title", ""),
                jd_text=job.get("jd_text", ""),
                location=job.get("location"),
                source=job.get("source", "job_feed"),
            )
        )
        enriched = dict(job)
        enriched.update(
            {
                "quality_decision": gate.decision,
                "quality_actionable": gate.actionable,
                "quality_role_key": gate.role_key,
                "quality_reasons": gate.reasons,
                "quality_blockers": gate.blockers,
                "quality_signals": gate.signals,
                "years_required": gate.years_required,
                "experience_risk": gate.experience_risk,
                "authorization_risk": gate.authorization_risk,
                "loaded_at": datetime.now(UTC).isoformat(),
            }
        )
        self._apply_structured_source_quality_overrides(enriched)
        self._apply_freshness_quality_overrides(enriched)
        self._apply_listing_page_quality_overrides(enriched)
        self._apply_public_remote_scope_quality_overrides(enriched)
        if enriched["quality_decision"] == "reject" and str(enriched.get("ai_verdict") or "") != "skip":
            enriched = self._drop_ai_fields(enriched)
        return enriched

    @staticmethod
    def _mark_current_source_active(job: dict, *, ats_type: str) -> dict:
        if ats_type not in {"ashby", "greenhouse", "lever"}:
            return job
        updated = dict(job)
        updated.setdefault("availability_status", "active")
        updated.setdefault("availability_reason", f"Listed in current {ats_type} refresh.")
        updated.setdefault("availability_checked_at", datetime.now(UTC).isoformat())
        return updated

    def _apply_unverified_posting_blocker(self, job: dict) -> None:
        blocker = "Could not fetch the live posting text before scoring this feed row."
        job["quality_blockers"] = [*job.get("quality_blockers", []), blocker]
        job["quality_decision"] = "reject"
        job["quality_actionable"] = False

    def _verify_job_availability(self, job: dict) -> dict:
        updated = dict(job)
        url = str(updated.get("discovered_url") or updated.get("url") or "").strip()
        if not url:
            return updated

        status, reason = self._job_availability(url)
        updated["availability_status"] = status
        updated["availability_checked_at"] = datetime.now(UTC).isoformat()
        if reason:
            updated["availability_reason"] = reason
        if status == "inactive":
            self._apply_inactive_posting_blocker(updated, reason or "Posting is no longer available.")
        return updated

    @staticmethod
    def _is_availability_reject(job: dict) -> bool:
        return str(job.get("availability_status") or "").lower() == "inactive"

    def _apply_inactive_posting_blocker(self, job: dict, reason: str) -> None:
        blocker = f"Posting availability blocker: {reason}"
        job["quality_blockers"] = [*job.get("quality_blockers", []), blocker]
        job["quality_decision"] = "reject"
        job["quality_actionable"] = False

    def _apply_listing_page_quality_overrides(self, job: dict) -> None:
        url = str(job.get("discovered_url") or job.get("url") or "")
        title = str(job.get("title") or "")
        text = str(job.get("jd_text") or "")
        if not url or not WebJobSearchService._looks_like_listing_page(title, url, text):
            return

        blocker = "Discovery result is a job listing/search page, not an individual open role."
        job["quality_blockers"] = [*job.get("quality_blockers", []), blocker]
        job["quality_decision"] = "reject"
        job["quality_actionable"] = False

    def _apply_public_remote_scope_quality_overrides(self, job: dict) -> None:
        source = str(job.get("source") or "").lower()
        if not any(term in source for term in ("remoteok", "remotejobs", "remotive", "the muse", "web search")):
            return

        location = self._normalize_location_scope_text(str(job.get("location") or ""))
        combined = self._normalize_location_scope_text(f"{job.get('location', '')}\n{job.get('jd_text', '')[:2500]}")
        if self._has_us_scope(combined):
            return
        if location in {"remote", "remote,", "flexible remote", "flexible / remote", "virtual"} or not location:
            blocker = "Public remote-board posting does not state United States eligibility."
            job["quality_blockers"] = [*job.get("quality_blockers", []), blocker]
            job["quality_decision"] = "reject"
            job["quality_actionable"] = False

    @staticmethod
    def _normalize_location_scope_text(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    @staticmethod
    def _has_us_scope(text: str) -> bool:
        return any(
            re.search(pattern, text)
            for pattern in (
                r"\bunited states\b",
                r"\busa\b",
                r"\bu s\b",
                r"\bus only\b",
                r"\bremote in usa\b",
            )
        )

    def _job_availability(self, url: str) -> tuple[str, str]:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host.endswith("ashbyhq.com"):
            return self._ashby_job_availability(parsed)
        if host.endswith("greenhouse.io"):
            return self._greenhouse_job_availability(parsed)
        return self._generic_job_availability(url)

    def _ashby_job_availability(self, parsed) -> tuple[str, str]:
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) < 2:
            return "unknown", ""
        slug, job_token = parts[0], parts[1]
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        try:
            with httpx.Client(
                timeout=20.0,
                follow_redirects=True,
                headers={"User-Agent": "CareerSiteAgent/1.0", "Accept": "application/json"},
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning("Ashby availability check failed for %s: %s", parsed.geturl(), exc)
            return "unknown", ""

        for item in payload.get("jobs", []):
            if not isinstance(item, dict):
                continue
            surfaces = " ".join(str(item.get(key) or "") for key in ("jobUrl", "applyUrl", "id"))
            if job_token in surfaces:
                if item.get("isListed") is False:
                    return "inactive", "Ashby posting is unlisted."
                return "active", "Listed in Ashby board API."
        return "inactive", "Ashby posting is no longer listed in the board API."

    def _greenhouse_job_availability(self, parsed) -> tuple[str, str]:
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        job_id = ""
        board_token = parts[0] if parts else ""
        if "jobs" in parts:
            index = parts.index("jobs")
            if index + 1 < len(parts):
                job_id = parts[index + 1]
        if not board_token or not job_id:
            query_job_id = (parse_qs(parsed.query).get("gh_jid") or [""])[0]
            return ("unknown", "") if not query_job_id else ("unknown", "Greenhouse custom-domain job needs page validation.")

        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}?content=true"
        try:
            with httpx.Client(
                timeout=20.0,
                follow_redirects=True,
                headers={"User-Agent": "CareerSiteAgent/1.0", "Accept": "application/json"},
            ) as client:
                response = client.get(url)
                if response.status_code in {404, 410}:
                    return "inactive", "Greenhouse posting is no longer listed in the board API."
                response.raise_for_status()
                return "active", "Listed in Greenhouse board API."
        except Exception as exc:
            logger.warning("Greenhouse availability check failed for %s: %s", parsed.geturl(), exc)
            return "unknown", ""

    def _generic_job_availability(self, url: str) -> tuple[str, str]:
        try:
            with httpx.Client(
                timeout=20.0,
                follow_redirects=True,
                headers={"User-Agent": "CareerSiteAgent/1.0"},
            ) as client:
                response = client.get(url)
                if response.status_code in {404, 410}:
                    return "inactive", f"HTTP {response.status_code} from posting page."
                response.raise_for_status()
                if self._response_looks_inactive(response):
                    return "inactive", "Posting page redirects to an error page or says the job is closed."
                return "active", "Posting page is reachable."
        except Exception as exc:
            logger.warning("Generic availability check failed for %s: %s", url, exc)
            return "unknown", ""

    @staticmethod
    def _response_looks_inactive(response: httpx.Response) -> bool:
        final = str(response.url).lower()
        if "error=true" in final or "job_not_found" in final:
            return True
        text = response.text[:5000].lower()
        inactive_markers = (
            "this job is no longer available",
            "this job posting is no longer available",
            "this position is no longer available",
            "no longer accepting applications",
            "job is closed",
            "position has been filled",
            "job not found",
            "posting is closed",
            "the job you are looking for is no longer open",
        )
        return any(marker in text for marker in inactive_markers)

    def _apply_freshness_quality_overrides(self, job: dict) -> None:
        age_hours = self._freshness_age_hours(job)
        if age_hours is None or age_hours <= RECOMMENDED_MAX_AGE_DAYS * 24:
            return

        age_days = round(age_hours / 24, 1)
        blocker = f"Posting is stale for recommendations: about {age_days:g} days old."
        job["quality_blockers"] = [*job.get("quality_blockers", []), blocker]
        job["quality_decision"] = "reject"
        job["quality_actionable"] = False

    def _apply_structured_source_quality_overrides(self, job: dict) -> None:
        blockers: list[str] = []
        reasons: list[str] = []
        signals: list[str] = []

        if job.get("is_clearance_required"):
            blockers.append("Structured source marks this role as clearance required.")
        if job.get("is_citizen_only"):
            blockers.append("Structured source marks this role as citizen-only.")

        try:
            min_years = float(job.get("min_years_required"))
        except (TypeError, ValueError):
            min_years = 0.0
        if min_years >= 2:
            blockers.append(f"Structured source minimum experience is above junior target: {min_years:g}+ years.")
        elif 0 < min_years <= 1.4:
            signals.append(f"Structured source minimum experience fits junior target: {min_years:g} years.")

        try:
            max_years = float(job.get("max_years_required"))
        except (TypeError, ValueError):
            max_years = 0.0
        if max_years > 2 and min_years < 2:
            reasons.append(f"Structured source experience range reaches above junior target: up to {max_years:g} years.")

        if job.get("is_h1b_sponsor"):
            signals.append("Structured source indicates H1B sponsor signal.")

        if not blockers and not reasons and not signals:
            return

        job["quality_blockers"] = [*job.get("quality_blockers", []), *blockers]
        job["quality_reasons"] = [*job.get("quality_reasons", []), *reasons]
        job["quality_signals"] = [*job.get("quality_signals", []), *signals]

        if blockers:
            job["quality_decision"] = "reject"
            job["quality_actionable"] = False
            job["experience_risk"] = "high" if any("experience" in blocker.lower() for blocker in blockers) else job.get("experience_risk")
            blocker_text = " ".join(blockers).lower()
            job["authorization_risk"] = "high" if any(
                term in blocker_text for term in ["clearance", "citizen"]
            ) else job.get("authorization_risk")
        elif reasons and job.get("quality_decision") == "pass":
            job["quality_decision"] = "review"
            job["quality_actionable"] = True

    def _load_targets(self) -> list[dict]:
        if not self.targets_path.exists():
            return []
        data = json.loads(self.targets_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []

    @staticmethod
    def _drop_ai_fields(job: dict) -> dict:
        updated = dict(job)
        for key in list(updated):
            if key.startswith("ai_"):
                updated.pop(key, None)
        return updated

    def _load_cache_payload(self) -> dict:
        return self._load_payload_from(self.cache_path)

    def _load_recent_cache_payload(self) -> dict:
        return self._load_payload_from(self.recent_cache_path)

    @staticmethod
    def _load_payload_from(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _persist_payload_to(payload: dict, path: Path) -> dict:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    def _recommendation_cache_jobs(
        self,
        cached_jobs: object,
        *,
        include_rejected: bool,
        max_age_days: int,
    ) -> list[dict]:
        if not isinstance(cached_jobs, list):
            return []

        kept: list[dict] = []
        for job in cached_jobs:
            if not isinstance(job, dict):
                continue
            reevaluated = self._enrich_job(job) if job.get("jd_text") else job
            if self._should_verify_cached_availability(reevaluated):
                reevaluated = self._verify_job_availability(reevaluated)
                if self._is_availability_reject(reevaluated):
                    continue
            if not include_rejected and self._is_cached_reject(reevaluated):
                continue
            age_hours = self._freshness_age_hours(reevaluated)
            if age_hours is not None and age_hours > max_age_days * 24:
                continue
            kept.append(reevaluated)
        return self._dedupe_jobs(kept)

    def _recent_cached_jobs(
        self,
        cached_jobs: object,
        *,
        hours: int,
        now: datetime,
        include_rejected: bool = False,
    ) -> list[dict]:
        if not isinstance(cached_jobs, list):
            return []

        recent_jobs: list[dict] = []
        for job in cached_jobs:
            if not isinstance(job, dict):
                continue
            if self._should_verify_cached_availability(job):
                job = self._verify_job_availability(job)
                if self._is_availability_reject(job):
                    continue
            if not include_rejected and self._is_cached_reject(job):
                continue
            age_hours = self._cached_job_age_hours(job, now=now)
            if age_hours is None or age_hours > hours:
                continue
            updated = dict(job)
            updated["freshness_hours"] = round(age_hours, 2)
            updated["freshness_label"] = WebJobSearchService._freshness_label(age_hours)
            updated.setdefault("freshness_window_hours", hours)
            recent_jobs.append(updated)
        return self._dedupe_jobs(recent_jobs)

    @staticmethod
    def _is_cached_reject(job: dict) -> bool:
        if str(job.get("quality_decision") or "").lower() == "reject":
            return True
        return job.get("quality_actionable") is False

    @staticmethod
    def _should_verify_cached_availability(job: dict) -> bool:
        if str(job.get("availability_status") or "").lower() == "inactive":
            return True
        if job.get("quality_actionable") is False:
            return False
        source = str(job.get("source") or "").lower()
        return (
            "simplify new grad" in source
            or "greenhouse" in source
            or "ashby" in source
            or "lever" in source
            or bool(job.get("cache_status"))
            or str(job.get("quality_decision") or "").lower() in {"pass", "review"}
        )

    def _cached_job_age_hours(self, job: dict, *, now: datetime) -> float | None:
        age_hours = self.web.posted_age_hours(self._job_posted_value(job), now=now)
        if age_hours is not None:
            return age_hours

        checked_age = self.web.posted_age_hours(job.get("freshness_checked_at"), now=now)
        try:
            original_age = float(job.get("freshness_hours"))
        except (TypeError, ValueError):
            return None
        if checked_age is None:
            return None
        return original_age + checked_age

    def _freshness_age_hours(self, job: dict) -> float | None:
        return self.web.posted_age_hours(self._job_posted_value(job))

    @staticmethod
    def _job_posted_value(job: dict) -> Any:
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

    def _sponsor_lookup(self, sponsors: list[dict]) -> dict[str, dict]:
        lookup: dict[str, dict] = {}
        for sponsor in sponsors:
            if not isinstance(sponsor, dict):
                continue
            key = self.h1b_sponsors.normalize_employer_name(str(sponsor.get("employer_name") or ""))
            if key:
                lookup[key] = sponsor
        return lookup

    def _with_dol_sponsor_signal(self, job: dict, sponsor_lookup: dict[str, dict]) -> dict:
        if not sponsor_lookup:
            return job
        company = str(job.get("company") or "")
        key = self.h1b_sponsors.normalize_employer_name(company)
        sponsor = sponsor_lookup.get(key)
        if not sponsor:
            return job

        updated = dict(job)
        updated["is_h1b_sponsor"] = True
        updated["h1b_sponsor_employer"] = sponsor.get("employer_name")
        updated["h1b_certified_lca_count"] = sponsor.get("certified_lca_count")
        updated["h1b_relevant_lca_count"] = sponsor.get("relevant_lca_count")
        updated["h1b_entry_level_lca_count"] = sponsor.get("entry_level_lca_count")
        updated["h1b_source_url"] = sponsor.get("source_url")
        updated["h1b_fiscal_year"] = sponsor.get("fiscal_year")
        updated["h1b_quarter"] = sponsor.get("quarter")
        return updated

    @staticmethod
    def _active_source_jobs(jobs: object) -> list[dict]:
        if not isinstance(jobs, list):
            return []
        active: list[dict] = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            source_text = " ".join(
                str(job.get(key) or "")
                for key in (
                    "source",
                    "source_vendor",
                    "source_detail_url",
                    "jd_text_source",
                    "discovered_url",
                    "url",
                )
            ).lower()
            if any(term in source_text for term in INACTIVE_SOURCE_TERMS):
                continue
            if str(job.get("availability_status") or "").lower() == "inactive":
                continue
            active.append(job)
        return active

    @classmethod
    def _merge_fresh_with_cached(cls, fresh_jobs: list[dict], cached_jobs: object, *, limit: int) -> list[dict]:
        if not isinstance(cached_jobs, list):
            cached_jobs = []

        merged: list[dict] = [*fresh_jobs]
        seen = {cls._job_identity(job) for job in fresh_jobs}
        for job in cached_jobs:
            if not isinstance(job, dict):
                continue
            key = cls._job_identity(job)
            if key in seen:
                continue
            preserved = dict(job)
            preserved.setdefault("cache_status", "preserved_from_previous_refresh")
            merged.append(preserved)
            seen.add(key)
            if len(merged) >= limit:
                break
        return cls._dedupe_jobs(merged)[:limit]

    @staticmethod
    def _job_identity(job: dict) -> str:
        key = (job.get("discovered_url") or job.get("url") or job.get("job_id") or "").strip().lower()
        if key:
            return key
        return "|".join(
            [
                str(job.get("company", "")).lower(),
                str(job.get("title", "")).lower(),
                str(job.get("location", "")).lower(),
            ]
        )

    @staticmethod
    def _dedupe_jobs(jobs: list[dict]) -> list[dict]:
        seen: set[str] = set()
        deduped: list[dict] = []
        for job in jobs:
            key = JobFeedService._job_identity(job)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(job)
        return deduped

    @staticmethod
    def _extract_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for node in soup(["script", "style", "nav", "footer", "header"]):
            node.decompose()

        preferred = []
        for selector in ["main", "article", ".content", ".job-description", ".job-post", "section"]:
            for node in soup.select(selector):
                text = node.get_text("\n", strip=True)
                if len(text) > 500:
                    preferred.append(text)
            if preferred:
                break

        text = "\n\n".join(preferred) if preferred else soup.get_text("\n", strip=True)
        meta_texts = []
        for attrs in [
            {"property": "og:description"},
            {"name": "description"},
            {"property": "twitter:description"},
            {"name": "twitter:description"},
        ]:
            node = soup.find("meta", attrs=attrs)
            content = str(node.get("content") or "") if node else ""
            if content:
                meta_texts.append(unescape(content))

        meta_text = "\n\n".join(meta_texts)
        lowered_text = text.lower()
        if meta_text and (
            not text.strip()
            or len(text.strip()) < 500
            or "you need to enable javascript" in lowered_text
        ):
            text = meta_text
        return re.sub(r"\n{3,}", "\n\n", text).strip()[:15000]
