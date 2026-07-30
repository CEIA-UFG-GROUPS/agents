"""Flight provider interface.

Any concrete provider (simulated now; SerpAPI Google Flights / Skyscanner later)
implements `search`. Agents depend on this interface, never on a concrete API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.flight import FlightOption, FlightSearchInput


class FlightProvider(ABC):
    """Abstract flight search provider."""

    name: str = "abstract"

    @abstractmethod
    def search(self, query: FlightSearchInput) -> list[FlightOption]:
        """Return candidate flights for the given query."""
        raise NotImplementedError
