"""MemoryAgent — reads traveler context, enriches origin, summarizes memory.

Memory RETRIEVAL is always deterministic (from the repository). The MemoryAgent
can also build a structured traveler profile and a trip-history summary; Gemini
may phrase the summary when LLM_ENABLED=true, but the underlying facts come only
from memory. See specs/agents.md (MemoryAgent).
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from app.agents.base import Agent, RunContext
from app.core.config import Settings, get_settings
from app.llm.gemini_client import build_gemini_client
from app.llm.prompts import build_memory_prompt
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import (
    MemoryEnrichment,
    MemoryItem,
    MemorySummary,
    MemoryWrite,
    TravelerProfile,
)
from app.schemas.trip import Location, TripIntent

logger = logging.getLogger("app.agents.memory")


class MemoryAgent(Agent):
    """Retrieves traveler preferences; enriches origin; summarizes memory."""

    name = "MemoryAgent"

    def __init__(
        self,
        repository: MemoryRepository | None = None,
        generate: Optional[Callable[[str], str]] = None,
        use_llm: Optional[bool] = None,
    ) -> None:
        self.repository = repository or MemoryRepository()
        self._generate = generate  # inject for tests
        self._use_llm = use_llm  # override settings (tests)

    def retrieve(self, context: RunContext | None = None) -> list[MemoryItem]:
        """Load the seeded traveler preferences (deterministic, offline)."""
        return self.repository.all()

    def enrich(self, intent: TripIntent, items: list[MemoryItem]) -> MemoryEnrichment:
        """Fill a missing origin from the traveler's home (city + airport).

        Never overrides an origin the user explicitly stated. Validation of the
        fields required for SEARCHING_FLIGHTS is done later (RESOLVING_LOCATIONS).
        """
        prefs = {item.key: item.content for item in items}
        home_city = prefs.get("home_city")
        home_airport = prefs.get("home_airport")

        origin_missing = intent.origin is None or (
            intent.origin.city is None and intent.origin.airport is None
        )
        if origin_missing and (home_city or home_airport):
            intent.origin = Location(city=home_city, airport=home_airport)
        return MemoryEnrichment(intent=intent)

    # --- summarization ---------------------------------------------------
    def build_profile(self, items: Optional[list[MemoryItem]] = None) -> TravelerProfile:
        """Build the structured traveler profile deterministically from memory."""
        items = items if items is not None else self.retrieve()
        prefs = {item.key: item.content for item in items}
        previous = [
            item.content
            for item in items
            if item.key == "previous_destination" or "destination" in item.tags
        ]
        return TravelerProfile(
            preferred_seat=prefs.get("preferred_seat_type"),
            preferred_hotel_chain=prefs.get("preferred_hotel_chain"),
            preferred_departure_window=prefs.get("preferred_departure_time"),
            previous_destinations=previous,
        )

    def summarize(self, items: Optional[list[MemoryItem]] = None) -> MemorySummary:
        """Return the traveler profile + a natural-language trip-history summary.

        Retrieval/profile are deterministic; only the prose summary may be phrased
        by Gemini (falling back to a deterministic summary when off or on error).
        """
        items = items if items is not None else self.retrieve()
        profile = self.build_profile(items)

        summary = _deterministic_summary(profile)
        if self._llm_enabled(get_settings()):
            try:
                phrased = self._summarize_with_gemini(profile)
                if phrased:
                    summary = phrased
            except Exception as exc:  # keep the deterministic summary
                logger.warning("Gemini memory summary failed; using fallback: %s", exc)
        return MemorySummary(traveler_profile=profile, trip_history_summary=summary)

    def _summarize_with_gemini(self, profile: TravelerProfile) -> Optional[str]:
        raw = self._call_model(build_memory_prompt(_profile_facts(profile)))
        if not raw:
            return None
        for line in raw.splitlines():
            text = line.strip().strip('"').strip("`").strip()
            if text:
                return text
        return None

    def _llm_enabled(self, settings: Settings) -> bool:
        return self._use_llm if self._use_llm is not None else settings.llm_enabled

    def _call_model(self, prompt: str) -> str:
        if self._generate is not None:
            return self._generate(prompt)
        client = build_gemini_client()
        if client is None:
            raise RuntimeError("LLM is disabled; cannot call Gemini")
        return client.generate(prompt)

    def remember(self, item: MemoryWrite) -> None:
        # TODO: write the learned itinerary summary back to memory (later phase).
        return None

    def run(self, context: RunContext) -> list[MemoryItem]:
        return self.retrieve(context)


# --- helpers --------------------------------------------------------------- #
def _deterministic_summary(profile: TravelerProfile) -> str:
    parts: list[str] = []
    prefs: list[str] = []
    if profile.preferred_seat:
        prefs.append(f"assento {profile.preferred_seat}")
    if profile.preferred_hotel_chain:
        prefs.append(f"rede {profile.preferred_hotel_chain}")
    if profile.preferred_departure_window:
        window = profile.preferred_departure_window
        prefs.append("partidas pela manhã" if window == "morning" else f"partidas {window}")
    if prefs:
        parts.append("Prefere " + _join_e(prefs) + ".")
    if profile.previous_destinations:
        parts.append("Já viajou para " + _join_e(profile.previous_destinations) + ".")
    return " ".join(parts) or "Sem preferências ou histórico registrados."


def _profile_facts(profile: TravelerProfile) -> str:
    return (
        f"assento preferido={profile.preferred_seat}; "
        f"rede de hotel preferida={profile.preferred_hotel_chain}; "
        f"janela de partida preferida={profile.preferred_departure_window}; "
        f"destinos anteriores={', '.join(profile.previous_destinations) or 'nenhum'}"
    )


def _join_e(items: list[str]) -> str:
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " e " + items[-1]
