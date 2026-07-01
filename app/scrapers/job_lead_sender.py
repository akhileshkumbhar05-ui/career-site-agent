from __future__ import annotations

import json
from typing import Any

import httpx


class JobLeadSender:
    def __init__(self, webhook_url: str, timeout: float = 30.0) -> None:
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send_job_lead(self, payload: dict[str, Any]) -> dict[str, Any] | str:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self.webhook_url, json=payload)
            response.raise_for_status()

            if response.content:
                try:
                    return response.json()
                except json.JSONDecodeError:
                    return response.text

            return {}