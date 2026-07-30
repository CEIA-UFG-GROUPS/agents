"""hotel_search_tool — hotel search via the hotel provider. See specs/tools.md."""

from __future__ import annotations

from app.schemas.hotel import HotelSearchInput, HotelSearchResult
from app.tools.providers.hotel_provider import HotelProvider
from app.tools.providers.simulated_hotel_provider import SimulatedHotelProvider


class HotelSearchTool:
    """Search hotels through the configured hotel provider."""

    name = "hotel_search_tool"

    def __init__(self, provider: HotelProvider | None = None) -> None:
        self.provider = provider or SimulatedHotelProvider()

    def search(self, query: HotelSearchInput) -> HotelSearchResult:
        options = self.provider.search(query)
        for option in options:
            option.source_tool = self.name  # observability: who surfaced it
        return HotelSearchResult(options=options)
