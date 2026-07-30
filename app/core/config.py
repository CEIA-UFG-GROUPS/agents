"""Application configuration.

Uses pydantic-settings so values can be overridden via environment variables
or a local .env file. Kept intentionally small for the teaching demo.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that mean "no real key" (e.g. the .env.example placeholder).
_PLACEHOLDER_API_KEYS = {"", "your_api_key_here", "changeme", "todo", "xxx"}


class Settings(BaseSettings):
    """Runtime settings for the corporate travel demo."""

    app_name: str = "Corporate Travel Multi-Agent Demo"
    app_version: str = "0.1.0"

    # Development seed mode. When true, the app ignores request payloads and runs
    # the pipeline from app/core/dev_seed.py:DEV_TRIP. Reads either DEV_MODE or
    # TRAVEL_DEV_MODE from the environment.
    dev_mode: bool = Field(
        default=False,
        validation_alias=AliasChoices("DEV_MODE", "TRAVEL_DEV_MODE"),
    )

    # Location/airport resolution. When LLM is enabled the Gemini provider is
    # used; otherwise the offline demo provider (fallback only) resolves airports.
    llm_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("LLM_ENABLED", "TRAVEL_LLM_ENABLED"),
    )
    gemini_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "TRAVEL_GEMINI_API_KEY"),
    )
    gemini_model: str = Field(
        default="gemini-3.5-flash",
        validation_alias=AliasChoices("GEMINI_MODEL", "TRAVEL_GEMINI_MODEL"),
    )
    gemini_advanced_model: str = Field(
        default="gemini-3.1-pro-preview",
        validation_alias=AliasChoices("GEMINI_ADVANCED_MODEL", "TRAVEL_GEMINI_ADVANCED_MODEL"),
    )

    @property
    def gemini_api_key_configured(self) -> bool:
        """True only when a real (non-placeholder) API key is set."""
        key = (self.gemini_api_key or "").strip()
        return bool(key) and key.lower() not in _PLACEHOLDER_API_KEYS

    @model_validator(mode="after")
    def _require_key_when_llm_enabled(self) -> "Settings":
        """Fail fast if the LLM is enabled but no real API key is configured."""
        if self.llm_enabled and not self.gemini_api_key_configured:
            raise ValueError(
                "LLM_ENABLED=true requires a real GEMINI_API_KEY in your .env "
                "(not empty or the placeholder 'your_api_key_here'). "
                "Set LLM_ENABLED=false to run offline."
            )
        return self

    # SQLite database location. Persistence is not wired up yet (skeleton stage),
    # but repositories are written to target this path.
    # TODO: create/connect this SQLite database in the repository layer.
    database_url: str = "sqlite:///./travel_demo.db"

    # Default trip/budget assumptions used by the (simulated) tools.
    default_currency: str = "BRL"
    default_per_diem_rate: float = 350.0
    default_origin: str = "GRU"
    # Year assumed when a request gives day/month but no year (e.g. "08 a 13 de junho").
    default_trip_year: int = 2026

    # Policy thresholds (illustrative).
    hotel_rate_cap: float = 450.0
    trip_budget_limit: float = 8000.0

    model_config = SettingsConfigDict(env_prefix="TRAVEL_", env_file=".env")


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (FastAPI dependency-friendly)."""

    return Settings()
