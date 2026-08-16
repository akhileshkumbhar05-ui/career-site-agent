from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_manual_jd_copilot_service
from app.schemas.copilot import (
    ConfirmApplicationLogRequest,
    ConfirmApplicationLogResponse,
    ManualJDAnalyzeRequest,
    ManualJDAnalyzeResponse,
    PrepareApplicationLogRequest,
    PrepareApplicationLogResponse,
)
from app.services.copilot_service import ManualJDCopilotService

router = APIRouter()


@router.post("/analyze-jd", response_model=ManualJDAnalyzeResponse)
def analyze_jd(
    payload: ManualJDAnalyzeRequest,
    service: ManualJDCopilotService = Depends(get_manual_jd_copilot_service),
) -> ManualJDAnalyzeResponse:
    return service.analyze(payload)


@router.post("/prepare-log", response_model=PrepareApplicationLogResponse)
def prepare_log(
    payload: PrepareApplicationLogRequest,
    service: ManualJDCopilotService = Depends(get_manual_jd_copilot_service),
) -> PrepareApplicationLogResponse:
    return service.prepare_log(payload)


@router.post("/confirm-log", response_model=ConfirmApplicationLogResponse)
def confirm_log(
    payload: ConfirmApplicationLogRequest,
    service: ManualJDCopilotService = Depends(get_manual_jd_copilot_service),
) -> ConfirmApplicationLogResponse:
    return service.confirm_log(payload)
