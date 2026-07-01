from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.application_packet import ApplicationPacketExportResponse
from app.schemas.ats_autofill import AutofillField, WatcherObserveResponse
from app.schemas.contact import OutreachDraftResponse, RecruiterContact
from app.schemas.pipeline import JobProcessRequest, JobProcessResponse
from app.schemas.queue import QueueProcessedItem
from app.schemas.tracker import ApplicationRowResponse


AgentName = Literal[
    "job_discovery",
    "fit_scoring",
    "resume_tailoring",
    "page_watcher",
    "recruiter_outreach",
    "tracker_email",
    "career_orchestrator",
]

AgentStepStatus = Literal["success", "warning", "error", "skipped"]


class AgentStep(BaseModel):
    agent: AgentName | str
    action: str
    status: AgentStepStatus = "success"
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class AgentCapabilitiesResponse(BaseModel):
    agents: list[dict[str, Any]]
    orchestration: dict[str, Any]


class JobDiscoveryAgentRequest(BaseModel):
    max_companies: int = Field(default=8, ge=1, le=50)
    max_jobs_per_company: int = Field(default=8, ge=1, le=50)
    include_rejected: bool = False
    include_web: bool = True
    web_max_results: int = Field(default=35, ge=1, le=100)
    include_cached: bool = True
    refresh_live: bool = True
    enqueue: bool = True
    use_llm: bool = True
    min_match_score: int = Field(default=70, ge=0, le=100)
    max_enqueue: int = Field(default=25, ge=0, le=200)
    priority: int = Field(default=100, ge=0, le=1000)


class DiscoveredJobSummary(BaseModel):
    company: str = ""
    title: str = ""
    location: str = ""
    source: str = ""
    discovered_url: str = ""
    score: int = 0
    verdict: str = ""
    queue_id: str = ""
    duplicate: bool = False
    reasons: list[str] = Field(default_factory=list)


class JobDiscoveryAgentResponse(BaseModel):
    discovered_count: int
    analyzed_count: int
    enqueued_count: int
    jobs: list[DiscoveredJobSummary]
    scrape_summary: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)


class FitScoringAgentRequest(BaseModel):
    job: JobProcessRequest
    use_llm: bool = True


class FitScoringAgentResponse(BaseModel):
    job: JobProcessRequest
    score: int
    verdict: str
    worth_applying: bool
    analysis: dict[str, Any]
    steps: list[AgentStep] = Field(default_factory=list)


class ResumeTailoringAgentRequest(BaseModel):
    queue_id: str = ""
    job: JobProcessRequest | None = None
    render_pdf: bool = True
    output_root_override: str = "data/outputs/agent_packets"
    update_queue: bool = False


class ResumeTailoringAgentResponse(BaseModel):
    decision: str = ""
    queue_id: str = ""
    pipeline_result: JobProcessResponse | None = None
    export_result: ApplicationPacketExportResponse | None = None
    steps: list[AgentStep] = Field(default_factory=list)


class PageWatcherAgentRequest(BaseModel):
    url: str = ""
    page_title: str = ""
    page_text: str = ""
    form_fields: list[AutofillField] = Field(default_factory=list)
    company: str = ""
    role: str = ""
    use_llm: bool = True
    fetch_if_empty: bool = True


class PageWatcherAgentResponse(BaseModel):
    observation: WatcherObserveResponse
    steps: list[AgentStep] = Field(default_factory=list)


class RecruiterOutreachAgentRequest(BaseModel):
    company: str
    title: str
    location: str = ""
    max_contacts: int = Field(default=5, ge=1, le=20)


class RecruiterOutreachAgentResponse(BaseModel):
    company: str
    contacts: list[RecruiterContact]
    drafts: list[OutreachDraftResponse]
    steps: list[AgentStep] = Field(default_factory=list)


class TrackerEmailAgentRequest(BaseModel):
    subject: str
    body: str
    sender_email: str = ""
    sender_name: str = ""
    update_local_tracker: bool = False
    company_override: str = ""
    role: str = ""


class TrackerEmailAgentResponse(BaseModel):
    classification: dict[str, Any]
    tracker_update: ApplicationRowResponse | None = None
    steps: list[AgentStep] = Field(default_factory=list)


class CareerPipelineAgentRequest(BaseModel):
    discover: JobDiscoveryAgentRequest = Field(default_factory=JobDiscoveryAgentRequest)
    process_limit: int = Field(default=5, ge=0, le=25)
    render_pdf: bool = True
    output_root_override: str = "data/outputs/agent_packets"
    worker_id: str = "career-agent-orchestrator"
    include_recruiter_outreach: bool = True
    include_page_watch: bool = True
    watch_use_llm: bool = False


class CareerPipelineAgentResponse(BaseModel):
    discovered: JobDiscoveryAgentResponse
    processed_items: list[QueueProcessedItem] = Field(default_factory=list)
    recruiter_outreach: list[RecruiterOutreachAgentResponse] = Field(default_factory=list)
    page_observations: list[PageWatcherAgentResponse] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
