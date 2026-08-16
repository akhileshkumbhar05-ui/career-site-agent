from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_application_sprint_service
from app.schemas.application_sprint import (
    ApplicationSprintAddItemsRequest,
    ApplicationSprintCreateRequest,
    ApplicationSprintResponse,
)
from app.services.application_sprint_service import ApplicationSprintConflict, ApplicationSprintService


router = APIRouter()


def _not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _conflict(exc: ApplicationSprintConflict) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.post("", response_model=ApplicationSprintResponse)
def create_sprint(
    payload: ApplicationSprintCreateRequest,
    service: ApplicationSprintService = Depends(get_application_sprint_service),
) -> ApplicationSprintResponse:
    try:
        return service.create(payload)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ApplicationSprintConflict as exc:
        raise _conflict(exc) from exc


@router.get("/current", response_model=ApplicationSprintResponse | None)
def get_current_sprint(
    service: ApplicationSprintService = Depends(get_application_sprint_service),
) -> ApplicationSprintResponse | None:
    return service.current()


@router.get("/{sprint_id}", response_model=ApplicationSprintResponse)
def get_sprint(
    sprint_id: str,
    service: ApplicationSprintService = Depends(get_application_sprint_service),
) -> ApplicationSprintResponse:
    try:
        return service.get(sprint_id)
    except KeyError as exc:
        raise _not_found(exc) from exc


@router.post("/{sprint_id}/items", response_model=ApplicationSprintResponse)
def add_sprint_items(
    sprint_id: str,
    payload: ApplicationSprintAddItemsRequest,
    service: ApplicationSprintService = Depends(get_application_sprint_service),
) -> ApplicationSprintResponse:
    try:
        return service.add_items(sprint_id, payload)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ApplicationSprintConflict as exc:
        raise _conflict(exc) from exc


@router.post("/{sprint_id}/pause", response_model=ApplicationSprintResponse)
def pause_sprint(
    sprint_id: str,
    service: ApplicationSprintService = Depends(get_application_sprint_service),
) -> ApplicationSprintResponse:
    try:
        return service.pause(sprint_id)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ApplicationSprintConflict as exc:
        raise _conflict(exc) from exc


@router.post("/{sprint_id}/resume", response_model=ApplicationSprintResponse)
def resume_sprint(
    sprint_id: str,
    service: ApplicationSprintService = Depends(get_application_sprint_service),
) -> ApplicationSprintResponse:
    try:
        return service.resume(sprint_id)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ApplicationSprintConflict as exc:
        raise _conflict(exc) from exc
