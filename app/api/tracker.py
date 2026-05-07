from fastapi import APIRouter, Depends

from app.dependencies import get_tracker_service
from app.schemas.tracker import (
    ApplicationRow,
    ApplicationRowCreateRequest,
    ApplicationRowResponse,
    ApplicationStatusUpdateRequest,
)
from app.services.tracker_service import TrackerService

router = APIRouter()


@router.post("/add-row", response_model=ApplicationRowResponse)
def add_row(
    payload: ApplicationRowCreateRequest,
    service: TrackerService = Depends(get_tracker_service),
) -> ApplicationRowResponse:
    return service.add_row(payload)


@router.post("/update-status", response_model=ApplicationRowResponse)
def update_status(
    payload: ApplicationStatusUpdateRequest,
    service: TrackerService = Depends(get_tracker_service),
) -> ApplicationRowResponse:
    return service.update_status(payload)


@router.get("/rows", response_model=list[ApplicationRow])
def list_rows(
    service: TrackerService = Depends(get_tracker_service),
) -> list[ApplicationRow]:
    return service.list_rows()