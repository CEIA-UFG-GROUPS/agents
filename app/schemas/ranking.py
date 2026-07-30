"""Ranking schemas — outputs of the Flight/Hotel ranking agents.

These agents score already-fetched options in-process (no tools). The ranking
logic itself is not implemented yet; these types define the contract.
See specs/agents.md (FlightRankingAgent, HotelRankingAgent).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.flight import FlightOption
from app.schemas.hotel import HotelOption


class RankedFlight(BaseModel):
    """A scored flight, ordered best-first by `rank`."""

    flight_id: str
    score: float
    rank: int
    reasons: list[str] = Field(default_factory=list)


class FlightRanking(BaseModel):
    """Full result of the FlightRankingAgent: the pick + the scored list."""

    recommended_flight: Optional[FlightOption] = None
    ranking: list[RankedFlight] = Field(default_factory=list)


class RankedHotel(BaseModel):
    """A scored hotel, ordered best-first by `rank`."""

    hotel_id: str
    score: float
    rank: int
    reasons: list[str] = Field(default_factory=list)


class HotelRanking(BaseModel):
    """Full result of the HotelRankingAgent: the pick + the scored list."""

    recommended_hotel: Optional[HotelOption] = None
    hotel_ranking: list[RankedHotel] = Field(default_factory=list)
