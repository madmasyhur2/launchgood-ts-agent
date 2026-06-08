"""
app/config.py

Centralised settings using pydantic-settings.
All values are read from environment variables or .env file.
"""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration.

    Pydantic-settings automatically reads values from environment variables
    (case-insensitive) and from a .env file if present.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # App
    # -------------------------------------------------------------------------
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    secret_key: str = "changeme-dev-secret"
    api_prefix: str = "/api"

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    database_url: str = (
        "postgresql+asyncpg://launchgood:launchgood_secret@localhost:5432/launchgood_ts"
    )

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # -------------------------------------------------------------------------
    # Celery
    # -------------------------------------------------------------------------
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # -------------------------------------------------------------------------
    # Google Gemini / LLM
    # -------------------------------------------------------------------------
    google_api_key: str = ""
    # Fast nodes: intake, content_analysis, compliance_check, fraud_signals, risk_scoring
    gemini_flash_model: str = "gemini-2.0-flash"
    # Reasoning node: decision
    gemini_pro_model: str = "gemini-2.5-pro-preview-06-05"

    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------
    allowed_origins: str = "http://localhost:3000"

    # -------------------------------------------------------------------------
    # Pagination
    # -------------------------------------------------------------------------
    default_page_size: int = 20
    max_page_size: int = 100

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: str) -> str:
        """Accept comma-separated string; stored as-is, parsed in main.py."""
        return v

    @property
    def allowed_origins_list(self) -> list[str]:
        """Return CORS origins as a Python list."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — reads env once per process lifetime."""
    return Settings()
