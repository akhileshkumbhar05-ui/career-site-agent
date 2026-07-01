from fastapi import APIRouter, Depends

from app.dependencies import get_career_agent_orchestrator_service
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
from app.services.career_agent_orchestrator_service import CareerAgentOrchestratorService

router = APIRouter()


@router.get("/capabilities", response_model=AgentCapabilitiesResponse)
def capabilities(
    service: CareerAgentOrchestratorService = Depends(get_career_agent_orchestrator_service),
) -> AgentCapabilitiesResponse:
    return service.capabilities()


@router.post("/discover-jobs", response_model=JobDiscoveryAgentResponse)
def discover_jobs(
    payload: JobDiscoveryAgentRequest,
    service: CareerAgentOrchestratorService = Depends(get_career_agent_orchestrator_service),
) -> JobDiscoveryAgentResponse:
    return service.discover_jobs(payload)


@router.post("/score-fit", response_model=FitScoringAgentResponse)
def score_fit(
    payload: FitScoringAgentRequest,
    service: CareerAgentOrchestratorService = Depends(get_career_agent_orchestrator_service),
) -> FitScoringAgentResponse:
    return service.score_fit(payload)


@router.post("/tailor-resume", response_model=ResumeTailoringAgentResponse)
def tailor_resume(
    payload: ResumeTailoringAgentRequest,
    service: CareerAgentOrchestratorService = Depends(get_career_agent_orchestrator_service),
) -> ResumeTailoringAgentResponse:
    return service.tailor_resume(payload)


@router.post("/observe", response_model=PageWatcherAgentResponse)
def observe_page(
    payload: PageWatcherAgentRequest,
    service: CareerAgentOrchestratorService = Depends(get_career_agent_orchestrator_service),
) -> PageWatcherAgentResponse:
    return service.observe_page(payload)


@router.post("/recruiter-outreach", response_model=RecruiterOutreachAgentResponse)
def recruiter_outreach(
    payload: RecruiterOutreachAgentRequest,
    service: CareerAgentOrchestratorService = Depends(get_career_agent_orchestrator_service),
) -> RecruiterOutreachAgentResponse:
    return service.recruiter_outreach(payload)


@router.post("/track-email", response_model=TrackerEmailAgentResponse)
def track_email(
    payload: TrackerEmailAgentRequest,
    service: CareerAgentOrchestratorService = Depends(get_career_agent_orchestrator_service),
) -> TrackerEmailAgentResponse:
    return service.track_email(payload)


@router.post("/run-pipeline", response_model=CareerPipelineAgentResponse)
def run_pipeline(
    payload: CareerPipelineAgentRequest,
    service: CareerAgentOrchestratorService = Depends(get_career_agent_orchestrator_service),
) -> CareerPipelineAgentResponse:
    return service.run_pipeline(payload)
