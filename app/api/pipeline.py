from fastapi import APIRouter, Depends

from app.dependencies import get_pipeline_service
from app.schemas.pipeline import JobProcessRequest, JobProcessResponse
from app.services.pipeline_service import PipelineService

router = APIRouter()


@router.post("/process-job", response_model=JobProcessResponse)
def process_job(
    payload: JobProcessRequest,
    service: PipelineService = Depends(get_pipeline_service),
) -> JobProcessResponse:
    return service.process_job(payload)