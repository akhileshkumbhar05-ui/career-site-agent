from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.agent import FitScoringAgentRequest, FitScoringAgentResponse
from app.services.job_feed_service import JobFeedService
from app.services.llm_match_service import LLMMatchService


class FitScoringAgent(BaseAgent):
    name = "fit_scoring"

    def __init__(self, *, feed: JobFeedService, matcher: LLMMatchService) -> None:
        self.feed = feed
        self.matcher = matcher

    def run(self, payload: FitScoringAgentRequest) -> FitScoringAgentResponse:
        job_dict = payload.job.model_dump()
        prepared = self.feed.ensure_jd_text(job_dict)
        analysis = self.matcher.analyze(prepared, use_llm=payload.use_llm)
        steps = [
            self.step(
                "score_fit",
                f"Scored {payload.job.title} at {payload.job.company}: {analysis.get('score')}%.",
                data={"scoring_mode": analysis.get("scoring_mode"), "verdict": analysis.get("verdict")},
            )
        ]
        return FitScoringAgentResponse(
            job=payload.job,
            score=int(analysis.get("score") or 0),
            verdict=str(analysis.get("verdict") or ""),
            worth_applying=bool(analysis.get("worth_applying")),
            analysis=analysis,
            steps=steps,
        )
