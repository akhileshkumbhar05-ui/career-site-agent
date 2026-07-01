from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.agent import (
    DiscoveredJobSummary,
    JobDiscoveryAgentRequest,
    JobDiscoveryAgentResponse,
)
from app.schemas.pipeline import JobProcessRequest
from app.schemas.queue import QueueEnqueueRequest
from app.services.job_feed_service import JobFeedService
from app.services.job_queue_service import JobQueueService
from app.services.llm_match_service import LLMMatchService


class JobDiscoveryAgent(BaseAgent):
    name = "job_discovery"

    def __init__(
        self,
        *,
        feed: JobFeedService,
        matcher: LLMMatchService,
        queue: JobQueueService,
    ) -> None:
        self.feed = feed
        self.matcher = matcher
        self.queue = queue

    def run(self, payload: JobDiscoveryAgentRequest) -> JobDiscoveryAgentResponse:
        steps = []
        scrape_summary: list[dict] = []
        if payload.refresh_live:
            refreshed = self.feed.refresh_live_jobs(
                max_companies=payload.max_companies,
                max_jobs_per_company=payload.max_jobs_per_company,
                include_rejected=payload.include_rejected,
                include_web=payload.include_web,
                web_max_results=payload.web_max_results,
            )
            scrape_summary = refreshed.get("targets", [])
            jobs = refreshed.get("all_jobs") or refreshed.get("jobs", [])
            steps.append(
                self.step(
                    "scrape_targets",
                    f"Scraped {len(scrape_summary)} configured/web targets and collected {len(jobs)} jobs.",
                    data={"targets": scrape_summary},
                )
            )
        elif payload.include_cached:
            jobs = self.feed.load_cached_jobs(limit=payload.max_companies * payload.max_jobs_per_company)
            steps.append(self.step("load_cache", f"Loaded {len(jobs)} jobs from local feed cache."))
        else:
            jobs = []
            steps.append(self.step("skip_discovery", "Live refresh and cache loading were both disabled.", status="warning"))

        summaries: list[DiscoveredJobSummary] = []
        enqueued = 0
        for job in jobs:
            prepared = self.feed.ensure_jd_text(job)
            analysis = self.matcher.analyze(prepared, use_llm=payload.use_llm)
            should_enqueue = (
                payload.enqueue
                and enqueued < payload.max_enqueue
                and analysis.get("worth_applying") is True
                and int(analysis.get("score") or 0) >= payload.min_match_score
                and analysis.get("verdict") != "skip"
            )

            queue_id = ""
            duplicate = False
            if should_enqueue:
                response = self.queue.enqueue(
                    QueueEnqueueRequest(
                        job=self._job_request(prepared),
                        priority=payload.priority,
                    )
                )
                queue_id = response.queue_id
                duplicate = response.duplicate
                if not duplicate:
                    enqueued += 1

            summaries.append(
                DiscoveredJobSummary(
                    company=str(prepared.get("company") or ""),
                    title=str(prepared.get("title") or ""),
                    location=str(prepared.get("location") or ""),
                    source=str(prepared.get("source") or ""),
                    discovered_url=str(prepared.get("discovered_url") or prepared.get("url") or ""),
                    score=int(analysis.get("score") or 0),
                    verdict=str(analysis.get("verdict") or ""),
                    queue_id=queue_id,
                    duplicate=duplicate,
                    reasons=list(analysis.get("risks") or analysis.get("quality_gate_reasons") or [])[:3],
                )
            )

        steps.append(
            self.step(
                "score_and_enqueue",
                f"Analyzed {len(summaries)} jobs and enqueued {enqueued} new high-fit leads.",
                data={"min_match_score": payload.min_match_score, "use_llm": payload.use_llm},
            )
        )

        return JobDiscoveryAgentResponse(
            discovered_count=len(jobs),
            analyzed_count=len(summaries),
            enqueued_count=enqueued,
            jobs=summaries,
            scrape_summary=scrape_summary,
            steps=steps,
        )

    @staticmethod
    def _job_request(job: dict) -> JobProcessRequest:
        return JobProcessRequest(
            job_id=str(job.get("job_id") or job.get("id") or ""),
            company=str(job.get("company") or ""),
            title=str(job.get("title") or ""),
            jd_text=str(job.get("jd_text") or ""),
            discovered_url=str(job.get("discovered_url") or job.get("url") or ""),
            source=str(job.get("source") or "job_discovery_agent"),
            posted_at=job.get("posted_at") or job.get("posted_date"),
            location=job.get("location") or "",
        )
