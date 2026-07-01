from fastapi import APIRouter

from app.config import settings
from app.services.llm_service import LLMService

router = APIRouter()
_llm = LLMService()


@router.get("/status")
def llm_status() -> dict:
    """Return the configured local LLM provider and availability."""
    available = _llm.is_available() if settings.llm_provider == "ollama" else False
    return {
        "provider": settings.llm_provider,
        "model": settings.ollama_model if settings.llm_provider == "ollama" else None,
        "ollama_url": settings.ollama_base_url if settings.llm_provider == "ollama" else None,
        "available": available,
    }
