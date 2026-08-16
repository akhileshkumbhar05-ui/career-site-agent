from __future__ import annotations

from app.schemas.application_loop import (
    ApplicationLoopATSOutcomeRequest,
    ApplicationLoopSheetLoggedRequest,
)
from app.schemas.ats_autofill import AutofillAutopilotContextRequest
from app.schemas.tracker import SheetsLogRequest, SheetsLogResponse
from app.schemas.third_eye_closeout import (
    ThirdEyeCloseoutProgress,
    ThirdEyeCloseoutRequest,
    ThirdEyeCloseoutResponse,
    ThirdEyeCloseoutReviewRequest,
    ThirdEyeCloseoutReviewResponse,
)
from app.services.application_loop_service import ApplicationLoopService, InvalidApplicationLoopTransition
from app.services.application_sprint_service import ApplicationSprintService
from app.services.autofill_autopilot_service import AutofillAutopilotService
from app.services.tracker_service import TrackerService


SUBMITTED_STATES = {"submitted_confirmed", "sheet_logged", "recruiter_note_ready", "outreach_done"}


class ThirdEyeCloseoutService:
    def __init__(
        self,
        *,
        loop_service: ApplicationLoopService,
        sprint_service: ApplicationSprintService,
        tracker: TrackerService,
        autofill_autopilot: AutofillAutopilotService,
    ) -> None:
        self.loop_service = loop_service
        self.sprint_service = sprint_service
        self.tracker = tracker
        self.autofill_autopilot = autofill_autopilot

    def review(self, payload: ThirdEyeCloseoutReviewRequest) -> ThirdEyeCloseoutReviewResponse:
        resolved = self._resolve(payload)
        if resolved is None:
            return ThirdEyeCloseoutReviewResponse(
                matched=False,
                reason=(
                    "Could not safely match this confirmation page to one open ATS application. "
                    "Open the application from its sprint job, then refresh this page."
                ),
                sheets_configured=self.tracker.sheets_configured,
                claude_calls=0,
            )

        item, match_source = resolved
        if item.ats_assist is None:
            return ThirdEyeCloseoutReviewResponse(
                matched=False,
                reason="The matched job has not been opened through ATS Apply Assist yet.",
                sheets_configured=self.tracker.sheets_configured,
                claude_calls=0,
            )
        return ThirdEyeCloseoutReviewResponse(
            matched=True,
            match_source=match_source,
            loop_item=item,
            submitted_sheet_row=self.loop_service.propose_sheet_row(item.loop_id, status="Applied"),
            technical_issue_sheet_row=self.loop_service.propose_sheet_row(
                item.loop_id,
                status="Not Yet Applied Due to Technical Issue",
            ),
            sheets_configured=self.tracker.sheets_configured,
            already_recorded=item.state in SUBMITTED_STATES or item.ats_assist.status == "technical_issue",
            claude_calls=0,
        )

    def commit(self, payload: ThirdEyeCloseoutRequest) -> ThirdEyeCloseoutResponse:
        item = self.loop_service.get_item(payload.loop_id)
        if item.ats_assist is None:
            raise InvalidApplicationLoopTransition("This job does not have an ATS Apply Assist handoff.")

        already_recorded = False
        if payload.outcome == "submitted_confirmed":
            if not payload.human_confirmed_submission:
                raise InvalidApplicationLoopTransition(
                    "Manual submission confirmation is required before marking this application Applied."
                )
            if item.state in SUBMITTED_STATES:
                already_recorded = True
            elif item.state == "ats_opened":
                outcome = self.loop_service.record_ats_outcome(
                    item.loop_id,
                    ApplicationLoopATSOutcomeRequest(
                        outcome="submitted_confirmed",
                        note=payload.note,
                        human_confirmed_submission=True,
                    ),
                )
                item = outcome.loop_item
            else:
                raise InvalidApplicationLoopTransition(
                    f"Submission cannot be confirmed from application state '{item.state}'."
                )
            status = "Applied"
        else:
            if item.state in SUBMITTED_STATES:
                raise InvalidApplicationLoopTransition("A submitted application cannot be changed to a portal issue.")
            if item.state != "ats_opened":
                raise InvalidApplicationLoopTransition(
                    f"A portal issue cannot be recorded from application state '{item.state}'."
                )
            if item.ats_assist.status == "technical_issue":
                already_recorded = True
            else:
                outcome = self.loop_service.record_ats_outcome(
                    item.loop_id,
                    ApplicationLoopATSOutcomeRequest(
                        outcome="technical_issue",
                        note=payload.note,
                    ),
                )
                item = outcome.loop_item
            status = "Not Yet Applied Due to Technical Issue"

        sheet_row = self.loop_service.propose_sheet_row(item.loop_id, status=status)
        sheet_row["Salary Quoted while Applying"] = payload.salary_quoted.strip() or "N/A"
        sheet_row["Job Posted On"] = payload.source.strip() or sheet_row["Job Posted On"]
        if payload.applied_using:
            sheet_row["Applied Using"] = payload.applied_using

        sheet_result = None
        if payload.log_to_sheets:
            if payload.outcome == "submitted_confirmed" and item.state in {
                "sheet_logged",
                "recruiter_note_ready",
                "outreach_done",
            }:
                sheet_result = SheetsLogResponse(
                    success=True,
                    message="This application was already logged to Sheets.",
                    mode="already_logged",
                )
            else:
                sheet_result = self.tracker.log_to_sheets(
                    SheetsLogRequest(
                        date=sheet_row["Date"],
                        company=sheet_row["Company Applied"],
                        role=sheet_row["Role"],
                        salary=sheet_row["Salary Quoted while Applying"],
                        job_posted_on=sheet_row["Job Posted On"],
                        applied_using=sheet_row["Applied Using"],
                        status=sheet_row["Status"],
                        link=sheet_row["Link"],
                        human_confirmed_submission=payload.human_confirmed_submission,
                        technical_issue=payload.outcome == "technical_issue",
                        notes=payload.note,
                    )
                )
                if (
                    sheet_result.success
                    and payload.outcome == "submitted_confirmed"
                    and item.state == "submitted_confirmed"
                ):
                    item = self.loop_service.mark_sheet_logged(
                        item.loop_id,
                        ApplicationLoopSheetLoggedRequest(
                            note=(
                                "Canonical Google Sheets row confirmed after manual submission."
                                if sheet_result.mode != "duplicate_skipped"
                                else "Canonical Google Sheets duplicate confirmed after manual submission."
                            ),
                            sheet_write_succeeded=True,
                        ),
                    )

        progress = self._progress()
        message = self._message(payload, sheet_result, progress, already_recorded)
        return ThirdEyeCloseoutResponse(
            outcome=payload.outcome,
            loop_item=item,
            sheet_row=sheet_row,
            sheet_result=sheet_result,
            sheet_logged=item.state in {"sheet_logged", "recruiter_note_ready", "outreach_done"},
            already_recorded=already_recorded,
            progress=progress,
            message=message,
            claude_calls=0,
        )

    def _resolve(self, payload: ThirdEyeCloseoutReviewRequest):
        if payload.loop_id:
            try:
                return self.loop_service.get_item(payload.loop_id), "explicit_loop"
            except KeyError:
                pass

        if payload.task_id:
            task = self.autofill_autopilot.get_task(payload.task_id)
            loop_id = str(task.get("loop_id") or "")
            if loop_id:
                try:
                    return self.loop_service.get_item(loop_id), "autofill_task"
                except KeyError:
                    pass

        context = self.autofill_autopilot.context(
            AutofillAutopilotContextRequest(
                url=payload.url,
                page_title=payload.page_title,
                page_text=payload.page_text,
            )
        )
        if context.enabled and context.loop_id:
            try:
                return self.loop_service.get_item(context.loop_id), "autofill_task"
            except KeyError:
                pass

        sprint = self.sprint_service.current()
        if sprint and sprint.current_loop_id:
            current = self.loop_service.get_item(sprint.current_loop_id)
            if current.state == "ats_opened" and current.ats_assist is not None:
                return current, "current_sprint"

        candidates = [
            item
            for item in self.loop_service.list_items(limit=100)
            if item.state == "ats_opened" and item.ats_assist is not None
        ]
        if len(candidates) == 1:
            return candidates[0], "single_open_ats"
        return None

    def _progress(self) -> ThirdEyeCloseoutProgress | None:
        sprint = self.sprint_service.current()
        if sprint is None:
            return None
        current = next((item for item in sprint.items if item.is_current), None)
        return ThirdEyeCloseoutProgress(
            sprint_id=sprint.sprint_id,
            sprint_name=sprint.name,
            sprint_status=sprint.status,
            target_count=sprint.stats.target_count,
            submitted_count=sprint.stats.submitted_count,
            sheet_logged_count=sprint.stats.sheet_logged_count,
            current_loop_id=sprint.current_loop_id,
            next_company=current.loop_item.company if current else "",
            next_role=current.loop_item.role if current else "",
            next_action=current.next_action.label if current else "",
            outreach_unlocked=sprint.outreach_unlocked,
        )

    @staticmethod
    def _message(payload, sheet_result, progress, already_recorded: bool) -> str:
        prefix = "This outcome was already recorded." if already_recorded else (
            "Manual submission confirmed." if payload.outcome == "submitted_confirmed" else "Portal issue recorded; this job was not marked Applied."
        )
        if not payload.log_to_sheets:
            return f"{prefix} The canonical Sheets row remains ready for review."
        if sheet_result and not sheet_result.success:
            return f"{prefix} Sheets logging failed: {sheet_result.message}"
        if payload.outcome == "technical_issue":
            return f"{prefix} The technical-issue row was logged to Sheets."
        if progress and progress.next_company:
            return f"{prefix} Sheets logging succeeded. The next sprint job is ready."
        if progress and progress.outreach_unlocked:
            return f"{prefix} Sheets logging succeeded. Recruiter outreach is unlocked."
        return f"{prefix} Sheets logging succeeded."
