from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.dependencies import (
    get_application_loop_service,
    get_third_eye_closeout_service,
    get_third_eye_intake_service,
)
from app.schemas.application_loop import (
    ApplicationLoopATSArmRequest,
    ApplicationLoopATSAssistResponse,
    ApplicationLoopATSOutcomeRequest,
    ApplicationLoopATSOutcomeResponse,
    ApplicationLoopBatchImportRequest,
    ApplicationLoopBatchItemRequest,
    ApplicationLoopBatchResponse,
    ApplicationLoopFitGateResponse,
    ApplicationLoopFitGateRunRequest,
    ApplicationLoopFitOverrideRequest,
    ApplicationLoopItem,
    ApplicationLoopJDUpdateRequest,
    ApplicationLoopMetricsResponse,
    ApplicationLoopMetricsWindow,
    ApplicationLoopOutreachBatchRequest,
    ApplicationLoopOutreachBatchResponse,
    ApplicationLoopOutreachResponse,
    ApplicationLoopOutreachSentRequest,
    ApplicationLoopOutreachUpdateRequest,
    ApplicationLoopSheetLoggedRequest,
    ApplicationLoopTailoringApproveRequest,
    ApplicationLoopTailoringApproveResponse,
    ApplicationLoopTailoringDraftRequest,
    ApplicationLoopTailoringDraftResponse,
    ApplicationLoopTailoringExportRequest,
    ApplicationLoopTailoringExportResponse,
    ApplicationLoopTailoringMemoryResponse,
    ThirdEyeIntakeRequest,
    ThirdEyeIntakeResponse,
    ThirdEyeIntakeReviewResponse,
)
from app.schemas.tailoring_review import TailoringPreviewRenderResponse, TailoringReviewSelection
from app.schemas.third_eye_closeout import (
    ThirdEyeCloseoutRequest,
    ThirdEyeCloseoutResponse,
    ThirdEyeCloseoutReviewRequest,
    ThirdEyeCloseoutReviewResponse,
)
from app.services.application_loop_service import ApplicationLoopService, InvalidApplicationLoopTransition
from app.services.third_eye_closeout_service import ThirdEyeCloseoutService
from app.services.third_eye_intake_service import ThirdEyeIntakeService


router = APIRouter()


@router.post("/batches", response_model=ApplicationLoopBatchResponse)
def import_batch(
    payload: ApplicationLoopBatchImportRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopBatchResponse:
    return service.import_batch(payload)


@router.post("/third-eye-intake/review", response_model=ThirdEyeIntakeReviewResponse)
def review_third_eye_intake(
    payload: ApplicationLoopBatchItemRequest,
    service: ThirdEyeIntakeService = Depends(get_third_eye_intake_service),
) -> ThirdEyeIntakeReviewResponse:
    return service.review(payload)


@router.post("/third-eye-intake", response_model=ThirdEyeIntakeResponse)
def commit_third_eye_intake(
    payload: ThirdEyeIntakeRequest,
    service: ThirdEyeIntakeService = Depends(get_third_eye_intake_service),
) -> ThirdEyeIntakeResponse:
    try:
        return service.commit(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/third-eye-closeout/review", response_model=ThirdEyeCloseoutReviewResponse)
def review_third_eye_closeout(
    payload: ThirdEyeCloseoutReviewRequest,
    service: ThirdEyeCloseoutService = Depends(get_third_eye_closeout_service),
) -> ThirdEyeCloseoutReviewResponse:
    return service.review(payload)


@router.post("/third-eye-closeout", response_model=ThirdEyeCloseoutResponse)
def commit_third_eye_closeout(
    payload: ThirdEyeCloseoutRequest,
    service: ThirdEyeCloseoutService = Depends(get_third_eye_closeout_service),
) -> ThirdEyeCloseoutResponse:
    try:
        return service.commit(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/items", response_model=list[ApplicationLoopItem])
def list_items(
    limit: int = Query(default=100, ge=1, le=500),
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> list[ApplicationLoopItem]:
    return service.list_items(limit=limit)


@router.get("/metrics", response_model=ApplicationLoopMetricsResponse)
def get_metrics(
    window: ApplicationLoopMetricsWindow = "7d",
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopMetricsResponse:
    return service.metrics(window)


@router.get("/tailoring-memory", response_model=ApplicationLoopTailoringMemoryResponse)
def get_tailoring_memory(
    role: str = Query(default="", max_length=500),
    exclude_loop_id: str = Query(default="", max_length=100),
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopTailoringMemoryResponse:
    return service.tailoring_memory(role, exclude_loop_id=exclude_loop_id)


@router.post("/fit-gate", response_model=ApplicationLoopFitGateResponse)
def run_fit_gate(
    payload: ApplicationLoopFitGateRunRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopFitGateResponse:
    return service.run_fit_gate(payload)


@router.post("/items/{loop_id}/fit-override", response_model=ApplicationLoopItem)
def override_fit_gate(
    loop_id: str,
    payload: ApplicationLoopFitOverrideRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopItem:
    try:
        return service.override_fit_gate(loop_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/items/{loop_id}/jd", response_model=ApplicationLoopItem)
def update_jd(
    loop_id: str,
    payload: ApplicationLoopJDUpdateRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopItem:
    try:
        return service.update_jd(loop_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/items/{loop_id}/sheet-logged", response_model=ApplicationLoopItem)
def mark_sheet_logged(
    loop_id: str,
    payload: ApplicationLoopSheetLoggedRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopItem:
    try:
        return service.mark_sheet_logged(loop_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/items/{loop_id}/tailoring/drafts",
    response_model=ApplicationLoopTailoringDraftResponse,
)
def create_tailoring_draft(
    loop_id: str,
    payload: ApplicationLoopTailoringDraftRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopTailoringDraftResponse:
    try:
        return service.create_tailoring_draft(loop_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get(
    "/items/{loop_id}/tailoring/draft",
    response_model=ApplicationLoopTailoringDraftResponse,
)
def get_tailoring_draft(
    loop_id: str,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopTailoringDraftResponse:
    try:
        return service.get_tailoring_draft(loop_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/items/{loop_id}/tailoring/preview",
    response_model=TailoringPreviewRenderResponse,
)
def render_tailoring_preview(
    loop_id: str,
    payload: TailoringReviewSelection,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> TailoringPreviewRenderResponse:
    try:
        return service.render_tailoring_preview(loop_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/items/{loop_id}/tailoring/approve",
    response_model=ApplicationLoopTailoringApproveResponse,
)
def approve_tailoring_draft(
    loop_id: str,
    payload: ApplicationLoopTailoringApproveRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopTailoringApproveResponse:
    try:
        return service.approve_tailoring_draft(loop_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/items/{loop_id}/tailoring/export",
    response_model=ApplicationLoopTailoringExportResponse,
)
def export_approved_tailoring(
    loop_id: str,
    payload: ApplicationLoopTailoringExportRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopTailoringExportResponse:
    try:
        return service.export_approved_tailoring(loop_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=422, detail=f"Could not write export files: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get(
    "/items/{loop_id}/tailoring/export",
    response_model=ApplicationLoopTailoringExportResponse,
)
def get_tailoring_export(
    loop_id: str,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopTailoringExportResponse:
    try:
        return service.get_tailoring_export(loop_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/items/{loop_id}/tailoring/download/{file_format}")
def download_tailoring_export(
    loop_id: str,
    file_format: str,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> FileResponse:
    try:
        path = service.download_tailoring_export(loop_id, file_format)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if file_format == "docx"
        else "application/pdf"
    )
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.post(
    "/items/{loop_id}/ats-assist/arm",
    response_model=ApplicationLoopATSAssistResponse,
)
def arm_ats_assist(
    loop_id: str,
    payload: ApplicationLoopATSArmRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopATSAssistResponse:
    try:
        return service.arm_ats_assist(loop_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Could not prepare ATS handoff: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get(
    "/items/{loop_id}/ats-assist",
    response_model=ApplicationLoopATSAssistResponse,
)
def sync_ats_assist(
    loop_id: str,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopATSAssistResponse:
    try:
        return service.sync_ats_assist(loop_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/items/{loop_id}/ats-assist/outcome",
    response_model=ApplicationLoopATSOutcomeResponse,
)
def record_ats_outcome(
    loop_id: str,
    payload: ApplicationLoopATSOutcomeRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopATSOutcomeResponse:
    try:
        return service.record_ats_outcome(loop_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/recruiter-outreach/batches",
    response_model=ApplicationLoopOutreachBatchResponse,
)
def prepare_recruiter_outreach_batch(
    payload: ApplicationLoopOutreachBatchRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopOutreachBatchResponse:
    try:
        return service.prepare_recruiter_outreach_batch(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put(
    "/items/{loop_id}/recruiter-outreach",
    response_model=ApplicationLoopOutreachResponse,
)
def update_recruiter_outreach(
    loop_id: str,
    payload: ApplicationLoopOutreachUpdateRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopOutreachResponse:
    try:
        return service.update_recruiter_outreach(loop_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/items/{loop_id}/recruiter-outreach/sent",
    response_model=ApplicationLoopOutreachResponse,
)
def mark_recruiter_outreach_sent(
    loop_id: str,
    payload: ApplicationLoopOutreachSentRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopOutreachResponse:
    try:
        return service.mark_recruiter_outreach_sent(loop_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApplicationLoopTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
