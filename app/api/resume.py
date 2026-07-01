from fastapi import APIRouter, Depends

from app.dependencies import (
    get_application_packet_export_service,
    get_decision_service,
    get_scoring_service,
    get_tailoring_service,
)
from app.schemas.application_packet import (
    ApplicationPacketExportRequest,
    ApplicationPacketExportResponse,
)
from app.schemas.resume import ResumeDecisionRequest, ResumeDecisionResponse, ResumeScoreRequest, ResumeScoreResponse, ResumeTailorRequest, ResumeTailorResponse
from app.services.application_packet_export_service import ApplicationPacketExportService
from app.services.decision_service import DecisionService
from app.services.scoring_service import ScoringService
from app.services.tailoring_service import TailoringService

router = APIRouter()


@router.post("/score", response_model=ResumeScoreResponse)
def score_resume(
    payload: ResumeScoreRequest,
    service: ScoringService = Depends(get_scoring_service),
) -> ResumeScoreResponse:
    return service.score(payload)


@router.post("/tailor", response_model=ResumeTailorResponse)
def tailor_resume(
    payload: ResumeTailorRequest,
    service: TailoringService = Depends(get_tailoring_service),
) -> ResumeTailorResponse:
    return service.tailor(payload)


@router.post("/decide", response_model=ResumeDecisionResponse)
def decide_resume_action(
    payload: ResumeDecisionRequest,
    service: DecisionService = Depends(get_decision_service),
) -> ResumeDecisionResponse:
    return service.decide(payload)


@router.post("/export-application-packet", response_model=ApplicationPacketExportResponse)
def export_application_packet(
    payload: ApplicationPacketExportRequest,
    service: ApplicationPacketExportService = Depends(get_application_packet_export_service),
) -> ApplicationPacketExportResponse:
    return service.export(payload)
