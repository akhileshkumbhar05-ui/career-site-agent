from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.dependencies import (
    get_application_loop_service,
    get_ats_autofill_service,
    get_autofill_autopilot_service,
    get_autofill_context_service,
    get_page_watcher_service,
    get_tailoring_review_service,
)
from app.services.application_loop_service import ApplicationLoopService, InvalidApplicationLoopTransition
from app.schemas.ats_autofill import (
    AutofillAutopilotArmRequest,
    AutofillAutopilotArmResponse,
    AutofillAutopilotContextRequest,
    AutofillAutopilotContextResponse,
    AutofillAutopilotResultRequest,
    AutofillAutopilotResultResponse,
    AutofillContextRequest,
    AutofillContextResponse,
    AutofillPlan,
    AutofillPreviewRequest,
    WatcherObserveRequest,
    WatcherObserveResponse,
)
from app.services.autofill_autopilot_service import AutofillAutopilotService
from app.services.autofill_context_service import AutofillContextService
from app.services.ats_autofill_service import ATSAutofillService
from app.services.page_watcher_service import PageWatcherService
from app.services.tailoring_review_service import TailoringReviewService
from app.schemas.tailoring_review import (
    TailoringDraftRequest,
    TailoringDraftResponse,
    TailoringFinalizeRequest,
    TailoringFinalizeResponse,
    TailoringPreviewRenderResponse,
)

router = APIRouter()


@router.post("/preview-html", response_model=AutofillPlan)
def preview_html_autofill(
    payload: AutofillPreviewRequest,
    service: ATSAutofillService = Depends(get_ats_autofill_service),
) -> AutofillPlan:
    return service.build_plan_from_html(
        html=payload.html,
        apply_plan=payload.apply_plan,
        source_url=payload.source_url,
    )


@router.get("/context", response_model=AutofillContextResponse)
def get_autofill_context(
    url: str = "",
    service: AutofillContextService = Depends(get_autofill_context_service),
) -> AutofillContextResponse:
    return service.load_or_prepare(AutofillContextRequest(url=url))


@router.post("/context", response_model=AutofillContextResponse)
def prepare_autofill_context(
    payload: AutofillContextRequest,
    service: AutofillContextService = Depends(get_autofill_context_service),
) -> AutofillContextResponse:
    return service.load_or_prepare(payload)


@router.post("/profile-context", response_model=AutofillContextResponse)
def prepare_profile_autofill_context(
    payload: AutofillContextRequest,
    service: ATSAutofillService = Depends(get_ats_autofill_service),
) -> AutofillContextResponse:
    apply_plan = service.build_profile_apply_plan(
        payload.url,
        {
            "company": payload.company,
            "title": payload.role,
            "source": payload.source,
            "discovered_url": payload.url,
        },
    )
    return AutofillContextResponse(
        source="profile_direct",
        confidence=0.72,
        apply_plan=apply_plan,
        message="Loaded saved application profile answers without preparing a packet.",
    )


@router.post("/autopilot/arm", response_model=AutofillAutopilotArmResponse)
def arm_autofill_autopilot(
    payload: AutofillAutopilotArmRequest,
    service: AutofillAutopilotService = Depends(get_autofill_autopilot_service),
) -> AutofillAutopilotArmResponse:
    return service.arm(payload)


@router.post("/autopilot/context", response_model=AutofillAutopilotContextResponse)
def get_autofill_autopilot_context(
    payload: AutofillAutopilotContextRequest,
    service: AutofillAutopilotService = Depends(get_autofill_autopilot_service),
) -> AutofillAutopilotContextResponse:
    return service.context(payload)


@router.post("/autopilot/result", response_model=AutofillAutopilotResultResponse)
def record_autofill_autopilot_result(
    payload: AutofillAutopilotResultRequest,
    service: AutofillAutopilotService = Depends(get_autofill_autopilot_service),
    loop_service: ApplicationLoopService = Depends(get_application_loop_service),
) -> AutofillAutopilotResultResponse:
    result = service.record_result(payload)
    if result.recorded and result.loop_id:
        try:
            loop_service.sync_ats_assist(result.loop_id)
        except (KeyError, InvalidApplicationLoopTransition, RuntimeError):
            pass
    return result


@router.post("/observe", response_model=WatcherObserveResponse)
def observe_page(
    payload: WatcherObserveRequest,
    service: PageWatcherService = Depends(get_page_watcher_service),
) -> WatcherObserveResponse:
    return service.observe(payload)


@router.post("/tailoring/preview", response_model=TailoringDraftResponse)
def preview_tailoring(
    payload: TailoringDraftRequest,
    service: TailoringReviewService = Depends(get_tailoring_review_service),
) -> TailoringDraftResponse:
    return service.create_draft(payload)


@router.post("/tailoring/finalize", response_model=TailoringFinalizeResponse)
def finalize_tailoring(
    payload: TailoringFinalizeRequest,
    service: TailoringReviewService = Depends(get_tailoring_review_service),
) -> TailoringFinalizeResponse:
    return service.finalize(payload)


@router.post("/tailoring/render-preview", response_model=TailoringPreviewRenderResponse)
def render_tailoring_preview(
    payload: TailoringFinalizeRequest,
    service: TailoringReviewService = Depends(get_tailoring_review_service),
) -> TailoringPreviewRenderResponse:
    return service.render_preview(payload)


@router.get("/tailoring/download/{draft_id}/{file_format}")
def download_tailored_resume(
    draft_id: str,
    file_format: str,
    service: TailoringReviewService = Depends(get_tailoring_review_service),
) -> FileResponse:
    path = service.download_path(draft_id, file_format)
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if file_format == "docx"
        else "application/pdf"
    )
    return FileResponse(path, media_type=media_type, filename=path.name)
