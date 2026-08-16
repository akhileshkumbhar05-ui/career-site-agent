from fastapi import APIRouter, Depends, Query

from app.dependencies import get_application_loop_service
from app.schemas.application_loop import (
    ApplicationLoopBatchImportRequest,
    ApplicationLoopBatchResponse,
    ApplicationLoopItem,
)
from app.services.application_loop_service import ApplicationLoopService


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
