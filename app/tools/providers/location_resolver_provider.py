"""Location resolver provider interface.

Concrete providers (Gemini LLM, or the offline demo fallback) turn a
LocationQuery into a ResolvedLocation. Agents/tools depend on this interface,
never on a concrete implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.location import LocationQuery, ResolvedLocation


class LocationResolverProvider(ABC):
    """Abstract airport/location resolver."""

    name: str = "abstract"

    @abstractmethod
    def resolve(self, query: LocationQuery) -> ResolvedLocation:
        """Resolve a place into an airport (or flag it for clarification)."""
        raise NotImplementedError
