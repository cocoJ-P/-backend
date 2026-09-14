"""Unified application settings.

All environment-driven configuration lives here. Domain and API modules
must read values from `settings` instead of duplicating defaults.
"""

from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    CORS_ORIGIN_REGEX: str = r"http://(localhost|127\.0\.0\.1):\d+"
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
    DEV_IDENTITY_ENABLED: bool = True
    FEISHU_ENABLED: bool = False
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: SecretStr = SecretStr("")
    FEISHU_BASE_URL: str = "https://open.feishu.cn"
    FEISHU_BITABLE_APP_TOKEN: str = ""
    FEISHU_SERVICE_CASE_TABLE_ID: str = ""
    FEISHU_REQUEST_TIMEOUT_SECONDS: float = 10

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                import json

                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value


settings = Settings()
