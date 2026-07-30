"""Gemini-backed location resolver provider.

Used when LLM_ENABLED=true. It asks Gemini (model from GEMINI_MODEL) to identify
the most likely commercial airport for a corporate-travel location and parses
the structured JSON reply. The google-genai client is reached through
GeminiClient (lazy import) so the package stays optional for the offline demo.

A `generate` callable can be injected for testing without hitting the network.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Optional

from app.core.config import get_settings
from app.llm.gemini_client import build_gemini_client
from app.llm.prompts import build_location_prompt
from app.schemas.location import AirportOption, LocationQuery, ResolvedLocation
from app.tools.providers.location_resolver_provider import LocationResolverProvider


class GeminiLocationResolverProvider(LocationResolverProvider):
    """Resolves airports via the Gemini API (structured JSON)."""

    name = "gemini"

    def __init__(
        self,
        model: Optional[str] = None,
        generate: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._model = model
        self._generate = generate  # inject for tests; otherwise uses GeminiClient

    def resolve(self, query: LocationQuery) -> ResolvedLocation:
        prompt = build_location_prompt(query)
        raw = self._call_model(prompt)
        data = json.loads(_extract_json(raw))
        return ResolvedLocation(
            city=data.get("city"),
            region=data.get("region"),
            country=data.get("country"),
            airport=data.get("airport"),
            airport_name=data.get("airport_name"),
            confidence=float(data.get("confidence") or 0.0),
            is_ambiguous=bool(data.get("is_ambiguous")),
            options=[_to_option(alt) for alt in (data.get("alternatives") or [])],
            reason=data.get("reason"),
        )

    def _call_model(self, prompt: str) -> str:
        if self._generate is not None:
            return self._generate(prompt)
        client = build_gemini_client()
        if client is None:
            raise RuntimeError("LLM is disabled; cannot call Gemini")
        return client.generate(prompt, model=self._model or get_settings().gemini_model)


def _to_option(alt: dict) -> AirportOption:
    return AirportOption(
        airport=alt.get("airport", ""),
        airport_name=alt.get("airport_name"),
        city=alt.get("city"),
        region=alt.get("region"),
        country=alt.get("country"),
    )


def _extract_json(text: str) -> str:
    """Pull the first JSON object out of the model's reply."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text
