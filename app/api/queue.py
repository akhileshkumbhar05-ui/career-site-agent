from fastapi import APIRouter, Depends, Query

from app.dependencies import get_application_orchestrator_service, get_job_queue_service
from app.schemas.queue import (
    JobQueueItem,
    QueueClaimRequest,
    QueueCompleteRequest,
    QueueEnqueueRequest,
    QueueEnqueueResponse,
    QueueProcessNextRequest,
    QueueProcessNextResponse,
    QueueStatus,
)
from app.services.application_orchestrator_service import ApplicationOrchestratorService
from app.services.job_queue_service import JobQueueService

router = APIRouter()


@router.post("/enqueue", response_model=QueueEnqueueResponse)
def enqueue_job(
    payload: QueueEnqueueRequest,
    orchestrator: ApplicationOrchestratorService = Depends(get_application_orchestrator_service),
) -> QueueEnqueueResponse:
    return orchestrator.enqueue(payload)


@router.get("/items", response_model=list[JobQueueItem])
def list_queue_items(
    status: QueueStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    queue: JobQueueService = Depends(get_job_queue_service),
) -> list[JobQueueItem]:
    return queue.list_items(status=status, limit=limit)


@router.post("/claim", response_model=list[JobQueueItem])
def claim_jobs(
    payload: QueueClaimRequest,
    queue: JobQueueService = Depends(get_job_queue_service),
) -> list[JobQueueItem]:
    return queue.claim(payload)


@router.post("/items/{queue_id}/complete", response_model=JobQueueItem)
def complete_job(
    queue_id: str,
    payload: QueueCompleteRequest,
    queue: JobQueueService = Depends(get_job_queue_service),
) -> JobQueueItem:
    return queue.complete(queue_id, payload)


@router.post("/process-next", response_model=QueueProcessNextResponse)
def process_next_jobs(
    payload: QueueProcessNextRequest,
    orchestrator: ApplicationOrchestratorService = Depends(get_application_orchestrator_service),
) -> QueueProcessNextResponse:
    return orchestrator.process_next(payload)
