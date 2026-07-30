"""Hotel provider interface.

Any concrete provider (simulated now; a real hotel/aggregator API later)
implements `search`. Agents depend on this interface, never on a concrete API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.hotel import HotelOption, HotelSearchInput


class HotelProvider(ABC):
    """Abstract hotel search provider."""

    name: str = "abstract"

    @abstractmethod
    def search(self, query: HotelSearchInput) -> list[HotelOption]:
        """Return candidate hotels for the given query."""
        raise NotImplementedError
