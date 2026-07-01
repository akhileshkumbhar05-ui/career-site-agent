from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.agent import TrackerEmailAgentRequest, TrackerEmailAgentResponse
from app.schemas.tracker import ApplicationStatusUpdateRequest
from app.services.email_classifier import classify_email
from app.services.tracker_service import TrackerService


class TrackerEmailAgent(BaseAgent):
    name = "tracker_email"

    def __init__(self, *, tracker: TrackerService) -> None:
        self.tracker = tracker

    def run(self, payload: TrackerEmailAgentRequest) -> TrackerEmailAgentResponse:
        classification = classify_email(
            subject=payload.subject,
            body=payload.body,
            sender_email=payload.sender_email,
            sender_name=payload.sender_name,
        )
        steps = [
            self.step(
                "classify_email",
                f"Classified email as {classification.get('email_type')} with {classification.get('confidence')} confidence.",
                data={
                    "new_status": classification.get("new_status"),
                    "requires_review": classification.get("requires_review"),
                    "is_job_related": classification.get("is_job_related"),
                },
            )
        ]

        tracker_update = None
        company = payload.company_override or classification.get("company_name") or ""
        if payload.update_local_tracker and company and payload.role and classification.get("new_status"):
            tracker_update = self.tracker.update_status(
                ApplicationStatusUpdateRequest(
                    company_applied=company,
                    role=payload.role,
                    status=classification["new_status"],
                    notes=classification.get("reasoning") or "",
                )
            )
            steps.append(self.step("update_local_tracker", f"Updated {company} / {payload.role}."))
        elif payload.update_local_tracker:
            steps.append(
                self.step(
                    "skip_tracker_update",
                    "Tracker update needs company, role, and a classified new status.",
                    status="warning",
                    data={"company": company, "role": payload.role},
                )
            )

        return TrackerEmailAgentResponse(
            classification=classification,
            tracker_update=tracker_update,
            steps=steps,
        )
