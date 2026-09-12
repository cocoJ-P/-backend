"""Unified application settings.

All environment-driven configuration lives here. Domain and API modules
must read values from `settings` instead of duplicating defaults.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    APP_NAME: str = "筑脉企服 Backend"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_PREFIX: str = "/api"
    DATABASE_URL: str = "sqlite:///./data/zumaix_enterprise_service.db"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    CONTENT_FETCH_TIMEOUT_SECONDS: float = 10
    CONTENT_MAX_BYTES: int = 5 * 1024 * 1024
    CONTENT_MAX_REDIRECTS: int = 5
    CONTENT_USER_AGENT: str = "ZumaixEnterpriseService/0.1"
    CONTENT_MIN_TEXT_LENGTH: int = 20
    CONTENT_EXCERPT_LENGTH: int = 400
    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_TIMEOUT_SECONDS: float = 60
    LLM_MAX_RETRIES: int = 2
    LLM_MAX_INPUT_CHARS: int = 24000

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


settings = Settings()
