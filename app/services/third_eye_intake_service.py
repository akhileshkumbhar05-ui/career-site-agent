from __future__ import annotations

from app.schemas.application_loop import (
    ApplicationLoopBatchImportRequest,
    ApplicationLoopBatchItemRequest,
    ThirdEyeIntakeRequest,
    ThirdEyeIntakeResponse,
    ThirdEyeIntakeReviewResponse,
    ThirdEyeSprintContext,
)
from app.schemas.application_sprint import ApplicationSprintAddItemsRequest, ApplicationSprintResponse
from app.services.application_loop_service import ApplicationLoopService
from app.services.application_sprint_service import ApplicationSprintConflict, ApplicationSprintService


class ThirdEyeIntakeService:
    def __init__(
        self,
        *,
        loop_service: ApplicationLoopService,
        sprint_service: ApplicationSprintService,
    ) -> None:
        self.loop_service = loop_service
        self.sprint_service = sprint_service

    def review(self, payload: ApplicationLoopBatchItemRequest) -> ThirdEyeIntakeReviewResponse:
        item_review = self.loop_service.review_batch_item(payload)
        sprint = self.sprint_service.current()
        already_in_sprint = bool(
            item_review.existing_loop_item
            and sprint
            and self._contains(sprint, item_review.existing_loop_item.loop_id)
        )
        sprint_context = self._sprint_context(sprint)
        return ThirdEyeIntakeReviewResponse(
            valid=item_review.valid,
            reason=item_review.reason,
            normalized_item=item_review.normalized_item,
            canonical_job_url=item_review.canonical_job_url,
            duplicate_reason=item_review.duplicate_reason,
            existing_loop_item=item_review.existing_loop_item,
            already_in_current_sprint=already_in_sprint,
            sprint=sprint_context,
            recommended_destination=(
                "active_sprint"
                if sprint_context and (sprint_context.accepts_items or already_in_sprint)
                else "inbox"
            ),
            claude_calls=0,
        )

    def commit(self, payload: ThirdEyeIntakeRequest) -> ThirdEyeIntakeResponse:
        item_payload = ApplicationLoopBatchItemRequest.model_validate(
            payload.model_dump(exclude={"destination"})
        )
        item_review = self.loop_service.review_batch_item(item_payload)
        if not item_review.valid:
            raise ValueError(item_review.reason)

        imported = self.loop_service.import_batch(
            ApplicationLoopBatchImportRequest(items=[item_payload])
        )
        outcome = imported.outcomes[0]
        if outcome.loop_item is None:
            raise ValueError(outcome.reason or "The job could not be added to the application inbox.")

        loop_item = outcome.loop_item
        duplicate_reason = outcome.reason if outcome.status == "duplicate" else ""
        if payload.destination == "inbox":
            return self._inbox_response(
                loop_item=loop_item,
                import_status=outcome.status,
                duplicate_reason=duplicate_reason,
                message=(
                    "This job is already in the Batch Inbox."
                    if outcome.status == "duplicate"
                    else "Added to the Batch Inbox."
                ),
            )

        sprint = self.sprint_service.current()
        if sprint and self._contains(sprint, loop_item.loop_id):
            return ThirdEyeIntakeResponse(
                action="duplicate_in_sprint",
                message=f"This job is already in {sprint.name}.",
                import_status=outcome.status,
                duplicate_reason=duplicate_reason,
                loop_item=loop_item,
                sprint=self._sprint_context(sprint),
                claude_calls=0,
            )

        sprint_context = self._sprint_context(sprint)
        if not sprint or not sprint_context or not sprint_context.accepts_items:
            reason = self._sprint_fallback_reason(sprint_context)
            return self._inbox_response(
                loop_item=loop_item,
                import_status=outcome.status,
                duplicate_reason=duplicate_reason,
                message=f"{reason} The job remains in the Batch Inbox.",
                sprint=sprint_context,
            )

        try:
            updated = self.sprint_service.add_items(
                sprint.sprint_id,
                ApplicationSprintAddItemsRequest(loop_ids=[loop_item.loop_id]),
            )
        except ApplicationSprintConflict as exc:
            return self._inbox_response(
                loop_item=loop_item,
                import_status=outcome.status,
                duplicate_reason=duplicate_reason,
                message=f"{exc} The job remains in the Batch Inbox.",
                sprint=self._sprint_context(self.sprint_service.current()),
            )

        return ThirdEyeIntakeResponse(
            action="added_to_sprint",
            message=f"Added to {updated.name}.",
            import_status=outcome.status,
            duplicate_reason=duplicate_reason,
            loop_item=loop_item,
            sprint=self._sprint_context(updated),
            claude_calls=0,
        )

    @staticmethod
    def _contains(sprint: ApplicationSprintResponse, loop_id: str) -> bool:
        return any(item.loop_item.loop_id == loop_id for item in sprint.items)

    @staticmethod
    def _sprint_context(sprint: ApplicationSprintResponse | None) -> ThirdEyeSprintContext | None:
        if sprint is None:
            return None
        return ThirdEyeSprintContext(
            sprint_id=sprint.sprint_id,
            name=sprint.name,
            status=sprint.status,
            open_slots=sprint.stats.open_slots,
            target_count=sprint.stats.target_count,
            active_job_count=sprint.stats.active_job_count,
            accepts_items=sprint.status in {"active", "paused"} and sprint.stats.open_slots > 0,
        )

    @staticmethod
    def _sprint_fallback_reason(sprint: ThirdEyeSprintContext | None) -> str:
        if sprint is None:
            return "There is no current sprint."
        if sprint.status == "completed":
            return f"{sprint.name} is complete."
        return f"{sprint.name} has no open slots."

    def _inbox_response(
        self,
        *,
        loop_item,
        import_status,
        duplicate_reason: str,
        message: str,
        sprint: ThirdEyeSprintContext | None = None,
    ) -> ThirdEyeIntakeResponse:
        return ThirdEyeIntakeResponse(
            action="duplicate_inbox" if import_status == "duplicate" else "added_to_inbox",
            message=message,
            import_status=import_status,
            duplicate_reason=duplicate_reason,
            loop_item=loop_item,
            sprint=sprint,
            claude_calls=0,
        )
