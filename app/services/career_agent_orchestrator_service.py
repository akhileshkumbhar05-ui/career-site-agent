from __future__ import annotations

from pathlib import Path

from app.agents.base import BaseAgent
from app.agents.fit_scoring_agent import FitScoringAgent
from app.agents.job_discovery_agent import JobDiscoveryAgent
from app.agents.page_watcher_agent import PageWatcherAgent
from app.agents.recruiter_outreach_agent import RecruiterOutreachAgent
from app.agents.resume_tailoring_agent import ResumeTailoringAgent
from app.agents.tracker_email_agent import TrackerEmailAgent
from app.schemas.agent import (
    AgentCapabilitiesResponse,
    CareerPipelineAgentRequest,
    CareerPipelineAgentResponse,
    FitScoringAgentRequest,
    FitScoringAgentResponse,
    JobDiscoveryAgentRequest,
    JobDiscoveryAgentResponse,
    PageWatcherAgentRequest,
    PageWatcherAgentResponse,
    RecruiterOutreachAgentRequest,
    RecruiterOutreachAgentResponse,
    ResumeTailoringAgentRequest,
    ResumeTailoringAgentResponse,
    TrackerEmailAgentRequest,
    TrackerEmailAgentResponse,
)
from app.schemas.queue import QueueProcessNextRequest
from app.services.application_orchestrator_service import ApplicationOrchestratorService


class CareerAgentOrchestratorService(BaseAgent):
    name = "career_orchestrator"

    def __init__(
        self,
        *,
        discovery_agent: JobDiscoveryAgent,
        scoring_agent: FitScoringAgent,
        tailoring_agent: ResumeTailoringAgent,
        watcher_agent: PageWatcherAgent,
        recruiter_agent: RecruiterOutreachAgent,
        tracker_email_agent: TrackerEmailAgent,
        queue_orchestrator: ApplicationOrchestratorService,
    ) -> None:
        self.discovery_agent = discovery_agent
        self.scoring_agent = scoring_agent
        self.tailoring_agent = tailoring_agent
        self.watcher_agent = watcher_agent
        self.recruiter_agent = recruiter_agent
        self.tracker_email_agent = tracker_email_agent
        self.queue_orchestrator = queue_orchestrator

    def capabilities(self) -> AgentCapabilitiesResponse:
        return AgentCapabilitiesResponse(
            agents=[
                {
                    "name": "job_discovery",
                    "goal": "Find profile-relevant jobs, reject obvious non-fits, and enqueue high-fit leads.",
                    "tools": ["Greenhouse scraper", "Lever scraper", "quality gate", "fit scorer", "SQLite queue"],
                },
                {
                    "name": "fit_scoring",
                    "goal": "Score a job against the candidate profile and decide apply/review/skip.",
                    "tools": ["JD parser", "resume scorer", "optional Claude/Ollama match reasoning"],
                },
                {
                    "name": "resume_tailoring",
                    "goal": "Create a tailored application packet and submission-ready resume artifacts.",
                    "tools": ["pipeline service", "resume tailoring service", "packet exporter", "PDF renderer"],
                },
                {
                    "name": "page_watcher",
                    "goal": "Watch any job/application page (any ATS), classify it, understand the JD, and suggest safe field fills. Fill on click; never submit.",
                    "tools": ["Claude page classifier", "JD understanding", "deterministic ATS field matcher", "browser Third Eye extension"],
                },
                {
                    "name": "recruiter_outreach",
                    "goal": "Find likely recruiters and draft concise LinkedIn/email outreach.",
                    "tools": ["LinkedIn search URL generator", "outreach draft service"],
                },
                {
                    "name": "tracker_email",
                    "goal": "Classify Gmail updates and update local tracking when company/role are known.",
                    "tools": ["email status rules", "tracker service", "Google Apps Script via n8n"],
                },
            ],
            orchestration={
                "primary_entrypoint": "POST /agents/run-pipeline",
                "n8n_role": "Schedule, trigger, and route agent runs; do not hold business logic.",
                "human_boundary": "Agents may prepare and prefill; final application submission remains manual.",
            },
        )

    def discover_jobs(self, payload: JobDiscoveryAgentRequest) -> JobDiscoveryAgentResponse:
        return self.discovery_agent.run(payload)

    def score_fit(self, payload: FitScoringAgentRequest) -> FitScoringAgentResponse:
        return self.scoring_agent.run(payload)

    def tailor_resume(self, payload: ResumeTailoringAgentRequest) -> ResumeTailoringAgentResponse:
        return self.tailoring_agent.run(payload)

    def observe_page(self, payload: PageWatcherAgentRequest) -> PageWatcherAgentResponse:
        return self.watcher_agent.run(payload)

    def recruiter_outreach(self, payload: RecruiterOutreachAgentRequest) -> RecruiterOutreachAgentResponse:
        return self.recruiter_agent.run(payload)

    def track_email(self, payload: TrackerEmailAgentRequest) -> TrackerEmailAgentResponse:
        return self.tracker_email_agent.run(payload)

    def run_pipeline(self, payload: CareerPipelineAgentRequest) -> CareerPipelineAgentResponse:
        steps = [
            self.step(
                "start_pipeline",
                "Starting local multi-agent job application pipeline.",
                data={"worker_id": payload.worker_id},
            )
        ]
        discovered = self.discovery_agent.run(payload.discover)
        steps.extend(discovered.steps)

        processed = []
        if payload.process_limit:
            queue_response = self.queue_orchestrator.process_next(
                QueueProcessNextRequest(
                    worker_id=payload.worker_id,
                    limit=payload.process_limit,
                    export_packet=True,
                    render_pdf=payload.render_pdf,
                    output_root_override=payload.output_root_override,
                )
            )
            processed = queue_response.items
            steps.append(
                self.step(
                    "process_queue",
                    f"Processed {queue_response.processed} queued jobs into scored/packet-ready states.",
                    data={"claimed": queue_response.claimed},
                )
            )

        page_observations = []
        if payload.include_page_watch:
            for item in processed:
                result = item.pipeline_result
                if not result or result.decision == "reject" or not result.official_url:
                    continue
                # Prefer the JD text the pipeline already saved (export job_description.txt);
                # fall back to fetching the live posting if it is not available.
                jd_text = self._processed_jd_text(item)
                try:
                    observation = self.watcher_agent.run(
                        PageWatcherAgentRequest(
                            url=result.official_url,
                            page_title=f"{result.title} at {result.company}",
                            page_text=jd_text,
                            company=result.company,
                            role=result.title,
                            use_llm=payload.watch_use_llm,
                            fetch_if_empty=True,
                        )
                    )
                except Exception:
                    continue
                page_observations.append(observation)
            steps.append(
                self.step(
                    "page_watch",
                    f"Page watcher reviewed {len(page_observations)} processed posting(s).",
                    data={"watched": len(page_observations)},
                )
            )

        outreach = []
        if payload.include_recruiter_outreach:
            for item in processed:
                result = item.pipeline_result
                if not result or result.decision == "reject":
                    continue
                outreach.append(
                    self.recruiter_agent.run(
                        RecruiterOutreachAgentRequest(
                            company=result.company,
                            title=result.title,
                            location="",
                            max_contacts=3,
                        )
                    )
                )
            steps.append(
                self.step(
                    "recruiter_outreach",
                    f"Prepared recruiter outreach for {len(outreach)} processed jobs.",
                )
            )

        return CareerPipelineAgentResponse(
            discovered=discovered,
            processed_items=processed,
            recruiter_outreach=outreach,
            page_observations=page_observations,
            steps=steps,
        )

    @staticmethod
    def _processed_jd_text(item) -> str:
        export = getattr(item, "export_result", None)
        jd_path = getattr(export, "jd_path", "") if export else ""
        if not jd_path:
            return ""
        try:
            path = Path(jd_path)
            if path.exists():
                return path.read_text(encoding="utf-8")[:16000]
        except Exception:
            return ""
        return ""
