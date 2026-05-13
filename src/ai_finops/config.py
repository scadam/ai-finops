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

    # Auth (API consumer auth)
    tenant_id: str = ""
    client_id: str = ""
    api_audience: str = "api://ai-finops"

    # ------------------------------------------------------------------
    # Microsoft SDK auth (used by every puller via MicrosoftAuthFactory)
    # ------------------------------------------------------------------
    azure_tenant_id: str = ""
    azure_client_id: str = ""          # User-Assigned MI client id (optional)
    azure_client_secret: str = ""      # local/dev fallback only

    # DB
    database_url: str = "sqlite:///./.data/ai_finops.sqlite"

    # Azure
    azure_subscription_id: str = ""
    focus_storage_account: str = ""
    focus_container: str = "focus-exports"
    purview_account_endpoint: str = ""

    # ------------------------------------------------------------------
    # Plug-and-play feature-flag matrix (Part 1 §1.3)
    # Customers enable a source only after the matching app-role is granted.
    # All default OFF so first deploy collects nothing it cannot explain.
    # ------------------------------------------------------------------
    ingest_agent365_enabled: bool = False
    ingest_entra_directory_enabled: bool = False
    ingest_entra_licensing_enabled: bool = False
    ingest_purview_enabled: bool = False
    ingest_defender_enabled: bool = False
    ingest_power_platform_enabled: bool = False
    ingest_azure_inventory_enabled: bool = False
    ingest_cost_management_enabled: bool = False
    ingest_graph_credits_enabled: bool = False
    ingest_graph_licenses_enabled: bool = False

    # ------------------------------------------------------------------
    # Modeller
    # ------------------------------------------------------------------
    modeler_config_dir: Path = Path("config/modeler")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def feature_flags(self) -> dict[str, bool]:
        """Return ``{job_name: enabled}`` for every plug-and-play source."""
        return {
            "agent365": self.ingest_agent365_enabled,
            "entra_directory": self.ingest_entra_directory_enabled,
            "entra_licensing": self.ingest_entra_licensing_enabled,
            "purview": self.ingest_purview_enabled,
            "defender": self.ingest_defender_enabled,
            "power_platform": self.ingest_power_platform_enabled,
            "azure_inventory": self.ingest_azure_inventory_enabled,
            "cost_management": self.ingest_cost_management_enabled,
            "graph_credits": self.ingest_graph_credits_enabled,
            "graph_licenses": self.ingest_graph_licenses_enabled,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Test helper — drop the lru_cache so a new env can be picked up."""
    get_settings.cache_clear()
