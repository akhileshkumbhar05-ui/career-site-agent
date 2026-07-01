from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.application_packet import ApplicationPacketExportResponse
from app.schemas.pipeline import JobProcessRequest, JobProcessResponse


QueueStatus = Literal[
    "discovered",
    "processing",
    "scored",
    "packet_ready",
    "prefill_ready",
    "manual_review",
    "submitted",
    "manually_skipped",
    "rejected",
    "failed",
]

TERMINAL_QUEUE_STATUSES = {"submitted", "manually_skipped", "rejected"}


class JobQueueItem(BaseModel):
    queue_id: str
    fingerprint: str
    job: JobProcessRequest
    status: QueueStatus
    priority: int
    attempts: int
    locked_by: Optional[str] = None
    locked_until: Optional[str] = None
    result: Optional[dict] = None
    error: str = ""
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None


class QueueEnqueueRequest(BaseModel):
    job: JobProcessRequest
    priority: int = Field(default=100, ge=0, le=1000)


class QueueEnqueueResponse(BaseModel):
    queue_id: str
    status: QueueStatus
    duplicate: bool
    message: str


class QueueClaimRequest(BaseModel):
    worker_id: str = "local-worker"
    limit: int = Field(default=1, ge=1, le=25)
    lease_seconds: int = Field(default=900, ge=30, le=7200)
    statuses: list[QueueStatus] = Field(default_factory=lambda: ["discovered"])


class QueueCompleteRequest(BaseModel):
    status: QueueStatus
    result: dict = Field(default_factory=dict)
    error: str = ""


class QueueProcessNextRequest(BaseModel):
    worker_id: str = "local-worker"
    limit: int = Field(default=1, ge=1, le=10)
    lease_seconds: int = Field(default=900, ge=30, le=7200)
    claim_statuses: list[QueueStatus] = Field(default_factory=lambda: ["discovered"])
    export_packet: bool = True
    render_pdf: bool = False
    output_root_override: Optional[str] = "data/outputs/queue_packets"


class QueueProcessedItem(BaseModel):
    queue_id: str
    status: QueueStatus
    pipeline_result: Optional[JobProcessResponse] = None
    export_result: Optional[ApplicationPacketExportResponse] = None
    error: str = ""


class QueueProcessNextResponse(BaseModel):
    worker_id: str
    claimed: int
    processed: int
    items: list[QueueProcessedItem]
