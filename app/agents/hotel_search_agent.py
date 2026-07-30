"""HotelSearchAgent — finds candidate hotels via the hotel tool.

Reads the traveler's preferred hotel chain from memory (passed through to the
tool) and calls hotel_search_tool. Ranking happens later in HotelRankingAgent.
See specs/agents.md.
"""

from __future__ import annotations

from app.agents.base import Agent, RunContext
from app.repositories.memory_repository import MemoryRepository
from app.schemas.hotel import HotelOption, HotelSearchInput
from app.schemas.trip import TripIntent
from app.tools.hotel_search_tool import HotelSearchTool


class HotelSearchAgent(Agent):
    """Queries hotel_search_tool for the stay dates."""

    name = "HotelSearchAgent"

    def __init__(self, hotel_search_tool=None, memory_repository=None) -> None:
        self.hotel_search_tool = hotel_search_tool or HotelSearchTool()
        self.memory_repository = memory_repository or MemoryRepository()

    def search(self, intent: TripIntent) -> list[HotelOption]:
        options, _ = self.search_with_trace(intent)
        return options

    def search_with_trace(
        self, intent: TripIntent
    ) -> tuple[list[HotelOption], dict]:
        """Call the hotel tool and return an explainability trace alongside.

        The trace records which preferences were applied, a per-tool call log,
        and a summary. Marking `preferred_match` is explainability only — it
        does NOT change which options are returned or their order.
        """
        prefs = {item.key: item.content for item in self.memory_repository.all()}
        preferred_chain = prefs.get("preferred_hotel_chain")

        destination = intent.destination
        query = HotelSearchInput(
            destination=(destination.city or destination.airport) if destination else None,
            check_in=intent.start_date,
            check_out=intent.end_date,
            guests=1,
            preferred_chain=preferred_chain,
        )
        options = self.hotel_search_tool.search(query).options

        # Flag preferred-chain matches (case-insensitive).
        for option in options:
            option.preferred_match = bool(preferred_chain) and (
                option.chain.lower() == preferred_chain.lower()
            )

        preferences_applied: dict = {}
        if preferred_chain:
            preferences_applied["preferred_hotel_chain"] = preferred_chain
        preferred_matches = sum(1 for option in options if option.preferred_match)

        trace = {
            "tool_calls": [{"tool": self.hotel_search_tool.name, "status": "success"}],
            "hotel_preferences_applied": preferences_applied,
            "search_summary": {
                "total_hotels_found": len(options),
                "preferred_matches": preferred_matches,
            },
        }
        return options, trace

    def run(self, context: RunContext) -> list[HotelOption]:
        return self.search(context["intent"])
