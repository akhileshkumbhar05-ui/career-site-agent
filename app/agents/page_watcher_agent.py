from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.agent import PageWatcherAgentRequest, PageWatcherAgentResponse
from app.schemas.ats_autofill import WatcherObserveRequest
from app.services.autofill_context_service import AutofillContextService
from app.services.page_watcher_service import PageWatcherService


class PageWatcherAgent(BaseAgent):
    """The "third eye" as an orchestrated agent.

    Given a job/application URL (or page text), it classifies the page, understands the JD,
    and proposes safe field fills. The browser extension drives this live on the page; the
    orchestrator drives the same capability server-side over a lead's posting.
    """

    name = "page_watcher"

    def __init__(self, *, watcher: PageWatcherService) -> None:
        self.watcher = watcher

    def run(self, payload: PageWatcherAgentRequest) -> PageWatcherAgentResponse:
        page_text = payload.page_text
        if not page_text.strip() and payload.fetch_if_empty and payload.url:
            page_text = AutofillContextService._fetch_page_text(payload.url)

        observation = self.watcher.observe(
            WatcherObserveRequest(
                url=payload.url,
                page_title=payload.page_title,
                page_text=page_text,
                form_fields=payload.form_fields,
                company=payload.company,
                role=payload.role,
                use_llm=payload.use_llm,
            )
        )

        jd = observation.jd
        summary = f"Classified page as {observation.page_type}"
        if jd and jd.role:
            summary += f"; read role '{jd.role}' at {jd.company or 'unknown company'}"
        if jd and jd.sponsorship_note:
            summary += f"; sponsorship note: {jd.sponsorship_note}"
        status = "success" if observation.page_type != "other" else "warning"

        return PageWatcherAgentResponse(
            observation=observation,
            steps=[
                self.step(
                    "observe_page",
                    summary,
                    status=status,
                    data={
                        "page_type": observation.page_type,
                        "engine": observation.engine,
                        "fillable_count": observation.fillable_count,
                        "sensitive_count": observation.sensitive_count,
                    },
                )
            ],
        )
