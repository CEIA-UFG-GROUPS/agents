"""DocumentAgent — generates the final travel justification/report.

Runs only after approval (GENERATING_REPORT → COMPLETED). It assembles a
TravelReport deterministically from existing TripRun data — no LLM, no tools.
See specs/agents.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.agents.base import Agent, RunContext
from app.schemas.approval import ApprovalResult, ApprovalStatus
from app.schemas.budget import BudgetEstimate
from app.schemas.flight import FlightOption
from app.schemas.hotel import HotelOption
from app.schemas.policy import PolicyResult
from app.schemas.recommendation import RecommendedTrip
from app.schemas.report import (
    ReportFlight,
    ReportHotel,
    ReportItinerary,
    TravelReport,
)
from app.schemas.trip import TripIntent


class DocumentAgent(Agent):
    """Builds the TravelReport from the approved trip's data."""

    name = "DocumentAgent"

    def generate(
        self,
        intent: Optional[TripIntent],
        recommended_flight: Optional[FlightOption],
        recommended_hotel: Optional[HotelOption],
        recommended_trip: Optional[RecommendedTrip],
        budget_estimate: Optional[BudgetEstimate],
        policy_result: Optional[PolicyResult],
        approval_result: Optional[ApprovalResult],
    ) -> Optional[TravelReport]:
        """Return the report, or None if the trip is not approved.

        Precondition: only an approved trip yields a report (pending/rejected
        return None and generate nothing).
        """
        if approval_result is None or approval_result.status is not ApprovalStatus.APPROVED:
            return None

        itinerary = ReportItinerary(
            origin=intent.origin.label if (intent and intent.origin) else None,
            destination=intent.destination.label if (intent and intent.destination) else None,
            start_date=intent.start_date if intent else None,
            end_date=intent.end_date if intent else None,
        )

        flight = None
        if recommended_flight is not None:
            flight = ReportFlight(
                airline=recommended_flight.airline,
                flight_number=recommended_flight.flight_number,
                departure_time=recommended_flight.departure_time,
                arrival_time=recommended_flight.arrival_time,
                price=recommended_flight.price,
                currency=recommended_flight.currency,
            )

        hotel = None
        if recommended_hotel is not None:
            hotel = ReportHotel(
                hotel_name=recommended_hotel.hotel_name,
                chain=recommended_hotel.chain,
                nights=recommended_hotel.nights,
                total_price=recommended_hotel.total_price,
                currency=recommended_hotel.currency,
            )

        justification = recommended_trip.justification if recommended_trip else []

        return TravelReport(
            title="Relatório de Viagem Corporativa",
            purpose=intent.purpose if intent else None,
            itinerary=itinerary,
            selected_flight=flight,
            selected_hotel=hotel,
            budget_summary=budget_estimate,
            policy_summary=policy_result,
            justification=list(justification),
            generated_at=datetime.now(timezone.utc),
        )

    def run(self, context: RunContext) -> Optional[TravelReport]:
        return self.generate(
            context.get("intent"),
            context.get("recommended_flight"),
            context.get("recommended_hotel"),
            context.get("recommended_trip"),
            context.get("budget_estimate"),
            context.get("policy_result"),
            context.get("approval_result"),
        )
