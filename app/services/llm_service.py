from __future__ import annotations

import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """Small Ollama wrapper with a silent fallback for rule-based services."""

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self.timeout = 90.0

    def generate(self, prompt: str, system: str = "") -> str:
        if settings.llm_provider != "ollama":
            return ""

        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 1024,
            },
        }
        if system:
            payload["system"] = system

        try:
            resp = httpx.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception as exc:
            logger.warning("LLMService.generate failed (%s); using rule-based fallback", exc)
            return ""

    def generate_json(self, prompt: str, system: str = "") -> dict:
        if settings.llm_provider != "ollama":
            return {}

        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_predict": 1400,
            },
        }
        if system:
            payload["system"] = system

        try:
            resp = httpx.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()
        except Exception as exc:
            logger.warning("LLMService.generate_json failed (%s); using rule-based fallback", exc)
            return {}

        if not raw:
            return {}

        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.splitlines()
            clean = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()
        if not clean.startswith("{"):
            start = clean.find("{")
            end = clean.rfind("}")
            if start >= 0 and end > start:
                clean = clean[start : end + 1]

        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            logger.warning("LLMService.generate_json failed to parse JSON: %s", raw[:200])
            return {}

    def is_available(self) -> bool:
        if settings.llm_provider != "ollama":
            return False

        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False
