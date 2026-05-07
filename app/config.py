from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CareerSite Agent"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    llm_provider: str = "mock"
    openai_api_key: str = ""
    google_sheets_spreadsheet_id: str = ""
    google_service_account_json: str = ""
    allowed_origins_raw: str = "http://localhost:3000,http://localhost:8501"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins_raw.split(",") if origin.strip()]


settings = Settings()
