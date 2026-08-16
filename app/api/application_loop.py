from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_application_loop_service
from app.schemas.application_loop import (
    ApplicationLoopBatchImportRequest,
    ApplicationLoopBatchResponse,
    ApplicationLoopFitGateResponse,
    ApplicationLoopFitGateRunRequest,
    ApplicationLoopFitOverrideRequest,
    ApplicationLoopItem,
    ApplicationLoopJDUpdateRequest,
)
from app.services.application_loop_service import ApplicationLoopService, InvalidApplicationLoopTransition


router = APIRouter()


@router.post("/batches", response_model=ApplicationLoopBatchResponse)
def import_batch(
    payload: ApplicationLoopBatchImportRequest,
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> ApplicationLoopBatchResponse:
    return service.import_batch(payload)


@router.get("/items", response_model=list[ApplicationLoopItem])
def list_items(
    limit: int = Query(default=100, ge=1, le=500),
    service: ApplicationLoopService = Depends(get_application_loop_service),
) -> list[ApplicationLoopItem]:
    return service.list_items(limit=limit)


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
