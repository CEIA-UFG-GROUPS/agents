"""location_resolver_tool — resolve a city/region/country into an airport.

Selects the Gemini provider when LLM is enabled, else the offline demo provider.
Applies the validation policy (3-letter IATA + confidence threshold); anything
that fails is returned with requires_clarification=true. See specs/tools.md.
"""

from __future__ import annotations

import logging
import re

from app.core.config import get_settings
from app.schemas.location import LocationQuery, ResolvedLocation
from app.tools.providers.gemini_location_resolver_provider import (
    GeminiLocationResolverProvider,
)
from app.tools.providers.location_resolver_provider import LocationResolverProvider
from app.tools.providers.offline_demo_location_resolver_provider import (
    OfflineDemoLocationResolverProvider,
)

CONFIDENCE_THRESHOLD = 0.80
_IATA_RE = re.compile(r"^[A-Z]{3}$")

logger = logging.getLogger("app.tools.location_resolver")


def build_default_location_provider() -> LocationResolverProvider:
    """Pick the resolver provider from configuration."""
    settings = get_settings()
    if settings.llm_enabled:
        return GeminiLocationResolverProvider(model=settings.gemini_model)
    return OfflineDemoLocationResolverProvider()


class LocationResolverTool:
    """Resolve a place into an airport, enforcing the validation policy."""

    name = "location_resolver_tool"

    def __init__(
        self,
        provider: LocationResolverProvider | None = None,
        fallback_provider: LocationResolverProvider | None = None,
    ) -> None:
        self.provider = provider or build_default_location_provider()
        # If the primary provider (e.g. Gemini) errors, fall back to the offline
        # demo provider so a usable region/country still resolves deterministically.
        if fallback_provider is not None:
            self.fallback_provider = fallback_provider
        elif self.provider.name != "offline_demo":
            self.fallback_provider = OfflineDemoLocationResolverProvider()
        else:
            self.fallback_provider = None

    def resolve(self, query: LocationQuery) -> ResolvedLocation:
        # Safe diagnostic — provider/model/location only, never the API key.
        location = query.location_text or query.city or query.free_text or ""
        model = get_settings().gemini_model if self.provider.name == "gemini" else "n/a"
        logger.info(
            'LocationResolverTool provider=%s model=%s location="%s"',
            self.provider.name, model, location,
        )
        try:
            result = self.provider.resolve(query)
        except Exception as exc:  # provider/LLM failure → deterministic fallback
            logger.warning("LocationResolverTool primary failed (%s); using fallback", exc)
            result = self._resolve_with_fallback(query, exc)
        if result.requires_clarification:
            return result
        # Validation rules → require clarification on any failure.
        if result.is_ambiguous:
            result.requires_clarification = True
            result.reason = result.reason or "ambiguous location"
        elif not _is_valid_iata(result.airport) or result.confidence < CONFIDENCE_THRESHOLD:
            result.requires_clarification = True
            result.reason = result.reason or "low confidence or invalid airport code"
        return result

    def _resolve_with_fallback(self, query: LocationQuery, exc: Exception) -> ResolvedLocation:
        """Resolve via the offline fallback; a controlled error if that fails too."""
        if self.fallback_provider is not None:
            try:
                return self.fallback_provider.resolve(query)
            except Exception as fallback_exc:  # pragma: no cover - defensive
                logger.warning("LocationResolverTool fallback failed: %s", fallback_exc)
        return ResolvedLocation(
            city=query.city,
            requires_clarification=True,
            reason=f"resolver error: {exc}",
        )


def _is_valid_iata(code: str | None) -> bool:
    return bool(code and _IATA_RE.match(code))
