from fastapi import APIRouter, Depends

from app.dependencies import get_recruiter_service
from app.schemas.contact import RecruiterLookupRequest, RecruiterLookupResponse, OutreachDraftRequest, OutreachDraftResponse
from app.services.recruiter_service import RecruiterService

router = APIRouter()


@router.post("/find-recruiter", response_model=RecruiterLookupResponse)
def find_recruiter(
    payload: RecruiterLookupRequest,
    service: RecruiterService = Depends(get_recruiter_service),
) -> RecruiterLookupResponse:
    return service.find_recruiter(payload)


@router.post("/draft-outreach", response_model=OutreachDraftResponse)
def draft_outreach(
    payload: OutreachDraftRequest,
    service: RecruiterService = Depends(get_recruiter_service),
) -> OutreachDraftResponse:
    return service.draft_outreach(payload)
