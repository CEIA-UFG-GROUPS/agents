"""Recommendation schema — output of the TravelRecommendationAgent.

Consolidates the already-chosen flight and hotel (plus their ranking reasons)
into one recommended trip with an estimated cost. It does NOT re-rank or call
tools — it only assembles prior agent outputs.
See specs/agents.md (TravelRecommendationAgent).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RecommendedTrip(BaseModel):
    """Lightweight recommendation artifact.

    References the selected flight/hotel by id rather than embedding full copies
    (those remain persisted in `flight_ranking.recommended_flight` and
    `recommended_hotel`). Carries the estimated cost and the justification.
    """

    flight_id: Optional[str] = None
    hotel_id: Optional[str] = None
    estimated_cost: float = 0.0
    currency: str = "BRL"
    justification: list[str] = Field(default_factory=list)
