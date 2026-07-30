"""skyscanner_tool — flight search via the Skyscanner provider.

Same input/output shape as google_flights_tool so results can be merged and
re-ranked. See specs/tools.md.
"""

from __future__ import annotations

from app.schemas.flight import FlightSearchInput, FlightSearchResult
from app.tools.providers.flight_provider import FlightProvider
from app.tools.providers.simulated_flight_provider import SimulatedFlightProvider


class SkyscannerTool:
    """Search flights through the configured (Skyscanner) provider."""

    name = "skyscanner_tool"

    def __init__(self, provider: FlightProvider | None = None) -> None:
        self.provider = provider or SimulatedFlightProvider(name="skyscanner")

    def search(self, query: FlightSearchInput) -> FlightSearchResult:
        options = self.provider.search(query)
        for option in options:
            option.source_tool = self.name  # observability: who surfaced it
        return FlightSearchResult(options=options)
