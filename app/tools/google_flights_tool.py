"""google_flights_tool (a.k.a. serpapi_google_flights_tool).

Thin wrapper over a FlightProvider. Ships with the simulated provider; swap in a
real SerpAPI Google Flights provider later without changing callers.
See specs/tools.md.
"""

from __future__ import annotations

from app.schemas.flight import FlightSearchInput, FlightSearchResult
from app.tools.providers.flight_provider import FlightProvider
from app.tools.providers.simulated_flight_provider import SimulatedFlightProvider

# Alias kept so the spec's alternative name resolves to the same tool.
serpapi_google_flights_tool = None  # set below


class GoogleFlightsTool:
    """Search flights through the configured flight provider."""

    name = "google_flights_tool"

    def __init__(self, provider: FlightProvider | None = None) -> None:
        self.provider = provider or SimulatedFlightProvider(name="google_flights")

    def search(self, query: FlightSearchInput) -> FlightSearchResult:
        options = self.provider.search(query)
        for option in options:
            option.source_tool = self.name  # observability: who surfaced it
        return FlightSearchResult(options=options)


serpapi_google_flights_tool = GoogleFlightsTool
