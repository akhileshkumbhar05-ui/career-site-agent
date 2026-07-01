from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.agent import ResumeTailoringAgentRequest, ResumeTailoringAgentResponse
from app.schemas.application_packet import ApplicationPacketExportRequest
from app.schemas.queue import QueueCompleteRequest
from app.services.application_packet_export_service import ApplicationPacketExportService
from app.services.job_queue_service import JobQueueService
from app.services.pipeline_service import PipelineService


class ResumeTailoringAgent(BaseAgent):
    name = "resume_tailoring"

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

    def run(self, payload: ResumeTailoringAgentRequest) -> ResumeTailoringAgentResponse:
        steps = []
        queue_id = payload.queue_id
        job = payload.job
        if queue_id:
            item = self.queue.get_item(queue_id)
            job = item.job
            steps.append(self.step("load_queue_item", f"Loaded queued job {queue_id}."))

        if job is None:
            return ResumeTailoringAgentResponse(
                decision="error",
                queue_id=queue_id,
                steps=[
                    self.step(
                        "validate_input",
                        "Provide either queue_id or job for resume tailoring.",
                        status="error",
                    )
                ],
            )

        pipeline_result = self.pipeline.process_job(job)
        steps.append(
            self.step(
                "run_pipeline",
                f"Pipeline decision: {pipeline_result.decision} for {job.title} at {job.company}.",
                data={"base_score": pipeline_result.base_score, "tailored_score": pipeline_result.tailored_score},
            )
        )

        export_result = None
        queue_status = "manual_review"
        queue_error = ""
        if pipeline_result.application_packet:
            export_result = self.packet_exporter.export(
                ApplicationPacketExportRequest(
                    application_packet=pipeline_result.application_packet,
                    output_root_override=payload.output_root_override,
                    selected_project_ids=pipeline_result.selected_project_ids,
                    changes_summary=pipeline_result.changes_summary or [pipeline_result.decision_reason],
                    summary_text=pipeline_result.summary_text,
                    rewritten_bullets=pipeline_result.rewritten_bullets,
                    connection_note=pipeline_result.connection_note or "",
                    jd_text=job.jd_text,
                    render_pdf=payload.render_pdf,
                )
            )
            queue_status = "packet_ready" if export_result.quality_passed else "manual_review"
            if payload.render_pdf and not export_result.pdf_rendered:
                queue_status = "failed"
                queue_error = export_result.pdf_error or "PDF rendering failed."
            steps.append(
                self.step(
                    "export_packet",
                    f"Exported application packet to {export_result.packet_folder_path}.",
                    data={"quality_passed": export_result.quality_passed, "pdf_rendered": export_result.pdf_rendered},
                )
            )
        else:
            queue_status = "rejected" if pipeline_result.decision == "reject" else "manual_review"
            steps.append(
                self.step(
                    "skip_export",
                    "No application packet was exported because the pipeline did not recommend applying.",
                    status="warning",
                    data={"decision": pipeline_result.decision},
                )
            )

        if payload.update_queue and queue_id:
            self.queue.complete(
                queue_id,
                QueueCompleteRequest(
                    status=queue_status,
                    result={
                        "pipeline_result": pipeline_result.model_dump(),
                        "export_result": export_result.model_dump() if export_result else None,
                    },
                    error=queue_error,
                ),
            )
            steps.append(self.step("update_queue", f"Updated queue item {queue_id} to {queue_status}."))

        return ResumeTailoringAgentResponse(
            decision=pipeline_result.decision,
            queue_id=queue_id,
            pipeline_result=pipeline_result,
            export_result=export_result,
            steps=steps,
        )
