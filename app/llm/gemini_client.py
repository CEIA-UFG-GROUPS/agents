"""Gemini client utility.

A thin wrapper around the google-genai SDK. The client is created lazily and
ONLY when LLM_ENABLED=true — when disabled, the app runs fully offline and never
touches this client. No Gemini calls are made here yet.
"""

from __future__ import annotations

from typing import Optional

from app.core.config import Settings, get_settings


class GeminiClient:
    """Holds Gemini configuration and lazily constructs the SDK client."""

    provider = "gemini"

    def __init__(self, api_key: str, model: str, advanced_model: str) -> None:
        self._api_key = api_key
        self.model = model
        self.advanced_model = advanced_model
        self._client = None  # constructed on first use

    @property
    def client(self):
        """Return the underlying google-genai client (created on first access)."""
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "google-genai is not installed; run `uv add google-genai`"
                ) from exc
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def generate(self, prompt: str, model: Optional[str] = None) -> str:
        """Generate text for a prompt and return the model's reply."""
        response = self.client.models.generate_content(
            model=model or self.model, contents=prompt
        )
        return response.text


def build_gemini_client(settings: Optional[Settings] = None) -> Optional[GeminiClient]:
    """Build a GeminiClient when LLM is enabled, else return None.

    Raises if LLM is enabled but the API key is missing (defensive — the same
    check runs in Settings validation at startup).
    """
    settings = settings or get_settings()
    if not settings.llm_enabled:
        return None
    if not settings.gemini_api_key_configured:
        raise RuntimeError("LLM_ENABLED=true but GEMINI_API_KEY is missing or a placeholder")
    return GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        advanced_model=settings.gemini_advanced_model,
    )


def llm_status(settings: Optional[Settings] = None) -> dict:
    """Safe, key-free status for diagnostics and the /tools/llm-status endpoint."""
    settings = settings or get_settings()
    return {
        "llm_enabled": settings.llm_enabled,
        "provider": "gemini",
        "model": settings.gemini_model,
        "api_key_configured": settings.gemini_api_key_configured,
    }
