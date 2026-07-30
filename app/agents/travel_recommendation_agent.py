"""TravelRecommendationAgent — consolidates the rankings into one recommendation.

Calls NO external tools and does NOT re-rank. It takes the already-chosen flight
and hotel plus their ranking reasons and assembles a `RecommendedTrip`:
estimated_cost = flight price + hotel total_price, and a justification built from
the prior agents' reasons. See specs/agents.md (TravelRecommendationAgent).
"""

from __future__ import annotations

from typing import Optional

from app.agents.base import Agent, RunContext
from app.schemas.flight import FlightOption
from app.schemas.hotel import HotelOption
from app.schemas.ranking import RankedFlight, RankedHotel
from app.schemas.recommendation import RecommendedTrip
from app.schemas.trip import TripIntent


class TravelRecommendationAgent(Agent):
    """Picks the top flight + hotel pair and explains the choice."""

    name = "TravelRecommendationAgent"

    def recommend(
        self,
        recommended_flight: Optional[FlightOption],
        recommended_hotel: Optional[HotelOption],
        flight_ranking: list[RankedFlight],
        hotel_ranking: list[RankedHotel],
        intent: Optional[TripIntent] = None,
    ) -> RecommendedTrip:
        if recommended_flight is None or recommended_hotel is None:
            return RecommendedTrip()

        # Reuse the reasons produced by the ranking agents (no re-ranking).
        flight_reasons = next(
            (r.reasons for r in flight_ranking if r.flight_id == recommended_flight.id),
            [],
        )
        hotel_reasons = next(
            (r.reasons for r in hotel_ranking if r.hotel_id == recommended_hotel.id),
            [],
        )
        justification = (
            [f"selected flight: {reason}" for reason in flight_reasons]
            + [f"selected hotel: {reason}" for reason in hotel_reasons]
        )

        estimated_cost = round(
            recommended_flight.price + recommended_hotel.total_price, 2
        )
        return RecommendedTrip(
            flight_id=recommended_flight.id,
            hotel_id=recommended_hotel.id,
            estimated_cost=estimated_cost,
            currency=recommended_flight.currency,
            justification=justification,
        )

    def run(self, context: RunContext) -> RecommendedTrip:
        return self.recommend(
            context.get("recommended_flight"),
            context.get("recommended_hotel"),
            context.get("flight_ranking", []),
            context.get("hotel_ranking", []),
            context.get("intent"),
        )
