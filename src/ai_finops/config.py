"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings — every field overridable via env or .env file."""

    model_config = SettingsConfigDict(
        env_prefix="AI_FINOPS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "dev"
    log_level: str = "INFO"

    # Rate card hot-reload
    rate_card_dir: Path = Path("config/rate_cards")
    rate_card_refresh_minutes: int = 60
    rate_card_stale_days: int = 7

    # CORS — comma-separated list
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Auth
    tenant_id: str = ""
    client_id: str = ""
    api_audience: str = "api://ai-finops"

    # DB
    database_url: str = ""

    # Azure
    azure_subscription_id: str = ""
    focus_storage_account: str = ""
    focus_container: str = "focus-exports"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
