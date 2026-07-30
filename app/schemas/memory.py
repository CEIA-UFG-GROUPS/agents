"""Memory schemas. See specs/tools.md (memory_tool)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.trip import TripIntent


class MemoryItem(BaseModel):
    """A single stored fact / traveler preference."""

    id: Optional[str] = None
    key: str
    content: str
    tags: list[str] = Field(default_factory=list)
    source: Literal["seed", "learned"] = "seed"


class MemoryQuery(BaseModel):
    """Read query against the memory store."""

    tags: Optional[list[str]] = None
    traveler: Optional[str] = None


class MemoryWrite(BaseModel):
    """Write request to the memory store."""

    key: str
    content: str
    tags: list[str] = Field(default_factory=list)


class MemoryReadResult(BaseModel):
    items: list[MemoryItem] = Field(default_factory=list)


class MemoryWriteResult(BaseModel):
    stored: bool = False
    id: Optional[str] = None


class MemoryEnrichment(BaseModel):
    """Outcome of MemoryAgent.enrich: the (possibly enriched) intent plus any
    open clarification the agent could not resolve from memory."""

    intent: TripIntent
    requires_clarification: bool = False
    clarification_question: Optional[str] = None


class TravelerProfile(BaseModel):
    """Structured traveler preferences (built deterministically from memory)."""

    preferred_seat: Optional[str] = None
    preferred_hotel_chain: Optional[str] = None
    preferred_departure_window: Optional[str] = None
    previous_destinations: list[str] = Field(default_factory=list)


class MemorySummary(BaseModel):
    """MemoryAgent summary: structured profile + a natural-language history."""

    traveler_profile: TravelerProfile
    trip_history_summary: str
