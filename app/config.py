import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ANTHROPIC_KEY_PATH = Path("Anthropic_API_Key.txt")


def load_project_anthropic_api_key(path: Path = PROJECT_ANTHROPIC_KEY_PATH) -> str:
    if not path.exists():
        return ""

    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if "=" in stripped:
            key, value = stripped.split("=", 1)
            if key.strip().upper() not in {"ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "CLAUDE_API_KEY"}:
                continue
            stripped = value.strip()

        return stripped.strip("\"'")

    return ""


class Settings(BaseSettings):
    app_name: str = "CareerSite Agent"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # LLM
    llm_provider: str = "mock"          # "mock" | "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Integrations
    google_apps_script_url: str = ""
    discord_webhook_url: str = ""

    # Legacy / reserved
    openai_api_key: str = ""
    google_sheets_spreadsheet_id: str = ""
    google_service_account_json: str = ""

    allowed_origins_raw: str = (
        "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8501,http://127.0.0.1:8501"
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins_raw.split(",")
            if origin.strip()
        ]


settings = Settings()
if not settings.anthropic_api_key and "pytest" not in sys.modules:
    settings.anthropic_api_key = load_project_anthropic_api_key()
