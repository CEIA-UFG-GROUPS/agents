"""BudgetAgent — estimates the total trip budget.

Consolidates the recommended flight + hotel with fixed travel assumptions (per
diem, local transport, contingency) into a transparent BudgetEstimate. The
formula is deterministic and the breakdown is printed for teaching.
See specs/agents.md (BudgetAgent) and app/core/budget_config.py.
"""

from __future__ import annotations

from typing import Optional

from app.agents.base import Agent, RunContext
from app.core.budget_config import (
    CONTINGENCY_RATE,
    DEFAULT_CURRENCY,
    LOCAL_TRANSPORT,
    PER_DIEM_RATE,
)
from app.schemas.budget import BudgetEstimate
from app.schemas.flight import FlightOption
from app.schemas.hotel import HotelOption
from app.schemas.trip import TripIntent


class BudgetAgent(Agent):
    """Totals flight + hotel + per-diem + local transport + contingency."""

    name = "BudgetAgent"

    def estimate(
        self,
        recommended_flight: Optional[FlightOption],
        recommended_hotel: Optional[HotelOption],
        intent: Optional[TripIntent] = None,
    ) -> BudgetEstimate:
        if recommended_flight is None or recommended_hotel is None:
            return BudgetEstimate()
        if intent is None or intent.start_date is None or intent.end_date is None:
            # Cannot derive date-based costs without the trip's start/end dates.
            return BudgetEstimate()

        # All date-based values are derived from the trip dates — no literals.
        start_date = intent.start_date
        end_date = intent.end_date
        span = (end_date - start_date).days
        inclusive_days = span + 1
        hotel_nights = span
        if inclusive_days <= 0 or hotel_nights < 0:
            raise ValueError(
                f"Invalid trip dates: {start_date} to {end_date} "
                f"(inclusive_days={inclusive_days}, hotel_nights={hotel_nights})"
            )

        currency = recommended_flight.currency or DEFAULT_CURRENCY

        flight_cost = round(recommended_flight.price, 2)
        hotel_cost = round(recommended_hotel.total_price, 2)
        per_diem = round(PER_DIEM_RATE * inclusive_days, 2)
        local_transport = round(float(LOCAL_TRANSPORT), 2)

        subtotal = flight_cost + hotel_cost + per_diem + local_transport
        contingency = round(subtotal * CONTINGENCY_RATE, 2)
        total = round(subtotal + contingency, 2)

        breakdown = [
            f"Trip dates: {start_date} to {end_date} "
            f"({inclusive_days} inclusive days, {hotel_nights} nights)",
            f"Flight: {flight_cost:.2f} {currency}",
            f"Hotel: {hotel_cost:.2f} {currency} ({hotel_nights} nights)",
            f"Per diem: {PER_DIEM_RATE} {currency} x {inclusive_days} days = {per_diem:.2f} {currency}",
            f"Local transport: {local_transport:.2f} {currency}",
            f"Contingency: {int(CONTINGENCY_RATE * 100)}% x {subtotal:.2f} = {contingency:.2f} {currency}",
        ]

        return BudgetEstimate(
            flight_cost=flight_cost,
            hotel_cost=hotel_cost,
            per_diem=per_diem,
            local_transport=local_transport,
            contingency=contingency,
            total=total,
            currency=currency,
            inclusive_days=inclusive_days,
            hotel_nights=hotel_nights,
            breakdown=breakdown,
        )

    def run(self, context: RunContext) -> BudgetEstimate:
        return self.estimate(
            context.get("recommended_flight"),
            context.get("recommended_hotel"),
            context.get("intent"),
        )
