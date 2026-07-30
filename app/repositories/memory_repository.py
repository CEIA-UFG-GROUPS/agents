"""MemoryRepository — stores traveler preferences and learnings.

SQLite-ready. For the skeleton it serves a fixed set of seed preferences so the
demo's memory step returns something useful. See specs/tools.md (memory_tool).
"""

from __future__ import annotations

from typing import Optional

from app.schemas.memory import MemoryItem

# Seed traveler preferences (see specs/agents.md — MemoryAgent).
# Deterministic and offline; `home_city` / `home_airport` let the MemoryAgent
# enrich a TripIntent whose origin the traveler did not state.
SEED_MEMORY: list[MemoryItem] = [
    MemoryItem(key="home_city", content="São Paulo", tags=["traveler", "origin"]),
    MemoryItem(key="home_airport", content="GRU", tags=["traveler", "origin"]),
    MemoryItem(key="preferred_departure_time", content="morning", tags=["flight", "preference"]),
    MemoryItem(key="preferred_hotel_chain", content="Quality", tags=["hotel", "preference"]),
    MemoryItem(key="avoid_overnight_flights", content="true", tags=["flight", "preference"]),
    MemoryItem(key="preferred_seat_type", content="window", tags=["flight", "preference"]),
    # Past trips (for the trip-history summary / previous destinations).
    MemoryItem(key="previous_destination", content="Belo Horizonte", tags=["history", "destination"]),
    MemoryItem(key="previous_destination", content="São Paulo", tags=["history", "destination"]),
    MemoryItem(key="previous_destination", content="Rio de Janeiro", tags=["history", "destination"]),
]


class MemoryRepository:
    """In-memory store of memory items (to be backed by SQLite later)."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        # TODO: open SQLite and load/seed the memory table.
        self.database_url = database_url
        self._items: list[MemoryItem] = list(SEED_MEMORY)

    def all(self) -> list[MemoryItem]:
        # TODO: SELECT all from the memory table.
        return list(self._items)

    def query(self, tags: Optional[list[str]] = None, traveler: Optional[str] = None) -> list[MemoryItem]:
        # TODO: filter by tags/traveler in SQL.
        if not tags:
            return self.all()
        return [item for item in self._items if any(t in item.tags for t in tags)]

    def add(self, item: MemoryItem) -> MemoryItem:
        # TODO: INSERT a learned item.
        self._items.append(item)
        return item
