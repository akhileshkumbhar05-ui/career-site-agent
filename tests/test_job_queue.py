import os
import shutil
from pathlib import Path

from app.dependencies import (
    get_application_orchestrator_service,
    get_application_packet_export_service,
    get_pipeline_service,
)
from app.schemas.pipeline import JobProcessRequest
from app.schemas.queue import (
    QueueClaimRequest,
    QueueCompleteRequest,
    QueueEnqueueRequest,
    QueueProcessNextRequest,
)
from app.services.application_orchestrator_service import ApplicationOrchestratorService
from app.services.job_queue_service import JobQueueService


def _sample_job(job_id: str = "queue_test_job") -> JobProcessRequest:
    return JobProcessRequest(
        job_id=job_id,
        company="Queue Test Labs",
        title="Junior Data Scientist",
        jd_text=(
            "We are hiring a Junior Data Scientist with 1 year of experience using "
            "Python, SQL, machine learning, pandas, scikit-learn, dashboards, and model evaluation. "
            "No citizenship or clearance requirement."
        ),
        discovered_url=f"https://example.com/jobs/{job_id}",
        source="pytest",
        location="Remote",
    )


def test_queue_dedupes_duplicate_leads():
    queue = JobQueueService()
    job = _sample_job("queue_dedupe_job")

    first = queue.enqueue(QueueEnqueueRequest(job=job))
    second = queue.enqueue(QueueEnqueueRequest(job=job))

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.queue_id == first.queue_id


def test_queue_claims_with_lease_and_completion():
    queue = JobQueueService()
    job = _sample_job("queue_claim_job")
    queued = queue.enqueue(QueueEnqueueRequest(job=job, priority=5))

    claimed = queue.claim(QueueClaimRequest(worker_id="worker-a", limit=1))
    assert any(item.queue_id == queued.queue_id for item in claimed)

    claimed_again = queue.claim(QueueClaimRequest(worker_id="worker-b", limit=1))
    assert all(item.queue_id != queued.queue_id for item in claimed_again)

    completed = queue.complete(
        queued.queue_id,
        QueueCompleteRequest(
            status="packet_ready",
            result={"packet": "created"},
        ),
    )

    assert completed.status == "packet_ready"
    assert completed.locked_by is None
    assert completed.result == {"packet": "created"}


def test_orchestrator_processes_next_job_into_packet_ready():
    output_dir = Path("data/outputs/test_job_queue") / str(os.getpid())
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    queue = JobQueueService()
    orchestrator = ApplicationOrchestratorService(
        queue=queue,
        pipeline=get_pipeline_service(),
        packet_exporter=get_application_packet_export_service(),
    )
    queued = queue.enqueue(QueueEnqueueRequest(job=_sample_job("queue_orchestrator_job"), priority=1))

    response = orchestrator.process_next(
        QueueProcessNextRequest(
            worker_id="pytest-worker",
            output_root_override=str(output_dir),
            render_pdf=False,
        )
    )

    assert response.processed >= 1
    processed = next(item for item in response.items if item.queue_id == queued.queue_id)
    assert processed.status == "packet_ready"
    assert processed.pipeline_result is not None
    assert processed.export_result is not None
    assert Path(processed.export_result.tailored_resume_html_path).exists()
    assert Path(processed.export_result.apply_plan_path).exists()
    assert Path(processed.export_result.ats_answers_path).exists()
