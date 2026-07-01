from app.schemas.application_packet import ApplicationPacketExportRequest
from app.schemas.queue import (
    QueueClaimRequest,
    QueueCompleteRequest,
    QueueEnqueueRequest,
    QueueEnqueueResponse,
    QueueProcessedItem,
    QueueProcessNextRequest,
    QueueProcessNextResponse,
)
from app.services.application_packet_export_service import ApplicationPacketExportService
from app.services.job_queue_service import JobQueueService
from app.services.pipeline_service import PipelineService


class ApplicationOrchestratorService:
    def __init__(
        self,
        *,
        queue: JobQueueService,
        pipeline: PipelineService,
        packet_exporter: ApplicationPacketExportService,
    ) -> None:
        self.queue = queue
        self.pipeline = pipeline
        self.packet_exporter = packet_exporter

    def enqueue(self, payload: QueueEnqueueRequest) -> QueueEnqueueResponse:
        return self.queue.enqueue(payload)

    def process_next(self, payload: QueueProcessNextRequest) -> QueueProcessNextResponse:
        claimed = self.queue.claim(
            QueueClaimRequest(
                worker_id=payload.worker_id,
                limit=payload.limit,
                lease_seconds=payload.lease_seconds,
                statuses=payload.claim_statuses,
            )
        )

        processed_items: list[QueueProcessedItem] = []
        for item in claimed:
            try:
                pipeline_result = self.pipeline.process_job(item.job)
                export_result = None
                next_status = self._status_after_pipeline(pipeline_result.decision)
                error = ""
                result_payload = {"pipeline_result": pipeline_result.model_dump()}

                if payload.export_packet and pipeline_result.application_packet is not None:
                    export_result = self.packet_exporter.export(
                        ApplicationPacketExportRequest(
                            application_packet=pipeline_result.application_packet,
                            output_root_override=payload.output_root_override,
                            selected_project_ids=pipeline_result.selected_project_ids,
                            changes_summary=pipeline_result.changes_summary
                            or [pipeline_result.decision_reason],
                            summary_text=pipeline_result.summary_text,
                            rewritten_bullets=pipeline_result.rewritten_bullets,
                            connection_note=pipeline_result.connection_note or "",
                            jd_text=item.job.jd_text,
                            render_pdf=payload.render_pdf,
                        )
                    )
                    result_payload["export_result"] = export_result.model_dump()

                    if payload.render_pdf and not export_result.pdf_rendered:
                        next_status = "failed"
                        error = export_result.pdf_error or "PDF rendering was requested but no PDF was rendered."
                    elif export_result.quality_passed:
                        next_status = "packet_ready"
                    else:
                        next_status = "manual_review"

                self.queue.complete(
                    item.queue_id,
                    QueueCompleteRequest(
                        status=next_status,
                        result=result_payload,
                        error=error,
                    ),
                )
                processed_items.append(
                    QueueProcessedItem(
                        queue_id=item.queue_id,
                        status=next_status,
                        pipeline_result=pipeline_result,
                        export_result=export_result,
                        error=error,
                    )
                )
            except Exception as exc:
                message = str(exc)
                self.queue.complete(
                    item.queue_id,
                    QueueCompleteRequest(status="failed", result={}, error=message),
                )
                processed_items.append(
                    QueueProcessedItem(
                        queue_id=item.queue_id,
                        status="failed",
                        error=message,
                    )
                )

        return QueueProcessNextResponse(
            worker_id=payload.worker_id,
            claimed=len(claimed),
            processed=len(processed_items),
            items=processed_items,
        )

    @staticmethod
    def _status_after_pipeline(decision: str) -> str:
        if decision == "reject":
            return "rejected"
        if decision == "manual_review":
            return "scored"
        return "scored"
