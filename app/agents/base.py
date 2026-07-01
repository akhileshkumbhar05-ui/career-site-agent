from __future__ import annotations

from typing import Any

from app.schemas.agent import AgentName, AgentStep, AgentStepStatus


class BaseAgent:
    name: AgentName | str = "career_orchestrator"

    def step(
        self,
        action: str,
        summary: str,
        *,
        status: AgentStepStatus = "success",
        data: dict[str, Any] | None = None,
    ) -> AgentStep:
        return AgentStep(
            agent=self.name,
            action=action,
            status=status,
            summary=summary,
            data=data or {},
        )
