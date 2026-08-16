from __future__ import annotations

import json
import uuid
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.schemas.ats_autofill import (
    AutofillAutopilotArmRequest,
    AutofillAutopilotArmResponse,
    AutofillAutopilotContextRequest,
    AutofillAutopilotContextResponse,
    AutofillAutopilotResultRequest,
    AutofillAutopilotResultResponse,
)
from app.services.ats_autofill_service import ATSAutofillService


class AutofillAutopilotService:
    """Stores one active browser autofill task for the local extension.

    The browser extension asks this service whether the current ATS page is
    armed for autofill. If it matches the active task, the extension receives
    the apply plan and fills only safe fields client-side.
    """

    def __init__(
        self,
        state_path: str = "data/runtime/autofill_autopilot.json",
        autofill: ATSAutofillService | None = None,
    ) -> None:
        self.state_path = Path(state_path)
        self.autofill = autofill or ATSAutofillService()

    def arm(self, payload: AutofillAutopilotArmRequest) -> AutofillAutopilotArmResponse:
        apply_plan = payload.apply_plan or self._load_apply_plan(payload.apply_plan_path)
        target_url = payload.url or str((apply_plan.get("job") or {}).get("official_url") or "")
        if not target_url:
            return AutofillAutopilotArmResponse(
                armed=False,
                message="No target URL was available for automated autofill.",
            )

        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=payload.expires_minutes)
        task = {
            "task_id": f"autofill_{uuid.uuid4().hex[:12]}",
            "loop_id": payload.loop_id,
            "status": "armed",
            "target_url": target_url,
            "apply_plan": apply_plan,
            "apply_plan_path": payload.apply_plan_path,
            "overwrite": payload.overwrite,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "last_result": {},
        }
        self._write_state(task)

        opened = False
        if payload.open_browser:
            try:
                opened = bool(webbrowser.open(target_url, new=2))
            except Exception:
                opened = False

        return AutofillAutopilotArmResponse(
            armed=True,
            task_id=task["task_id"],
            loop_id=payload.loop_id,
            target_url=target_url,
            apply_plan_path=payload.apply_plan_path,
            expires_at=expires_at.isoformat(),
            opened_browser=opened,
            message=(
                "Saved-profile autofill is armed. Open the target ATS page in the browser with "
                "the CareerSite extension installed; safe fields will be filled automatically. "
                "Tailored resume packets are optional."
                if not payload.apply_plan_path
                else (
                    "Automated autofill is armed from a prepared application plan. Open the target ATS page "
                    "in the browser with the CareerSite extension installed; safe fields will be filled automatically."
                )
            ),
        )

    def context(self, payload: AutofillAutopilotContextRequest) -> AutofillAutopilotContextResponse:
        task = self._read_state()
        if not task:
            return AutofillAutopilotContextResponse(enabled=False, message="No active autofill task.")
        if self._is_expired(task):
            self.clear()
            return AutofillAutopilotContextResponse(enabled=False, message="Autofill task expired.")
        if not self._page_matches_task(payload, task):
            return AutofillAutopilotContextResponse(enabled=False, message="Current page does not match active task.")

        task["status"] = "active"
        task["last_seen_url"] = payload.url
        task["last_seen_at"] = datetime.now(UTC).isoformat()
        self._write_state(task)
        return AutofillAutopilotContextResponse(
            enabled=True,
            task_id=str(task.get("task_id") or ""),
            loop_id=str(task.get("loop_id") or ""),
            overwrite=bool(task.get("overwrite")),
            apply_plan=task.get("apply_plan") or {},
            apply_plan_path=str(task.get("apply_plan_path") or ""),
            message="Matched active autofill task.",
        )

    def record_result(self, payload: AutofillAutopilotResultRequest) -> AutofillAutopilotResultResponse:
        task = self._read_state()
        if not task or payload.task_id != task.get("task_id"):
            return AutofillAutopilotResultResponse(recorded=False, message="No matching active task.")

        task["status"] = "filled"
        task["last_result"] = payload.model_dump()
        task["last_result_at"] = datetime.now(UTC).isoformat()
        self._write_state(task)
        return AutofillAutopilotResultResponse(
            recorded=True,
            loop_id=str(task.get("loop_id") or ""),
            message="Autofill result recorded.",
        )

    def get_task(self, task_id: str = "") -> dict[str, Any]:
        task = self._read_state()
        if not task or (task_id and task_id != task.get("task_id")):
            return {}
        return task

    def clear(self) -> None:
        if self.state_path.exists():
            self.state_path.unlink()

    def _page_matches_task(self, payload: AutofillAutopilotContextRequest, task: dict[str, Any]) -> bool:
        current_url = payload.url or ""
        target_url = str(task.get("target_url") or "")
        apply_plan = task.get("apply_plan") or {}
        job = dict(apply_plan.get("job") or {})
        if target_url and not job.get("official_url"):
            job["official_url"] = target_url

        score = self.autofill._score_apply_plan_url_match(current_url, job)
        if score >= 0.82:
            return True

        current_host = urlparse(current_url).netloc.lower()
        target_host = urlparse(target_url).netloc.lower()
        if current_host and target_host and (
            current_host == target_host
            or current_host.endswith(target_host)
            or target_host.endswith(current_host)
        ):
            return True

        page_text = f"{payload.page_title} {payload.page_text}".lower()
        company = str(job.get("company") or "").lower()
        role_tokens = self.autofill._meaningful_tokens(str(job.get("role") or ""))
        if company and company in page_text and sum(1 for token in role_tokens if token in page_text) >= 2:
            return True

        return False

    def _read_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_state(self, task: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(task, indent=2), encoding="utf-8")

    @staticmethod
    def _load_apply_plan(path: str) -> dict[str, Any]:
        if not path:
            return {}
        return json.loads(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def _is_expired(task: dict[str, Any]) -> bool:
        expires_raw = str(task.get("expires_at") or "")
        if not expires_raw:
            return True
        try:
            return datetime.fromisoformat(expires_raw) <= datetime.now(UTC)
        except ValueError:
            return True
