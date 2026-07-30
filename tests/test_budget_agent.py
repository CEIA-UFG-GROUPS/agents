"""Unit tests for BudgetAgent date-derived calculations."""

from __future__ import annotations

from datetime import date

import pytest

from app.agents.budget_agent import BudgetAgent
from app.schemas.flight import FlightOption
from app.schemas.hotel import HotelOption
from app.schemas.trip import TripIntent


def _flight() -> FlightOption:
    return FlightOption(
        id="f1",
        provider="google_flights",
        airline="Azul",
        flight_number="AD-4110",
        origin_airport="GYN",
        destination_airport="CNF",
        departure_time="2026-07-08T11:20:00",
        arrival_time="2026-07-08T12:45:00",
        duration_minutes=85,
        stops=0,
        price=455.50,
        currency="BRL",
    )


def _hotel(nights: int = 5) -> HotelOption:
    return HotelOption(
        id="h1",
        provider="hotel_sim",
        hotel_name="Quality Hotel Belo Horizonte",
        chain="Quality",
        stars=4.0,
        distance_km=2.1,
        nightly_rate=320.0,
        nights=nights,
        total_price=320.0 * nights,
        currency="BRL",
    )


def test_inclusive_days_and_hotel_nights_july():
    """2026-07-08 -> 2026-07-13 => 6 inclusive days, 5 hotel nights."""
    intent = TripIntent(start_date=date(2026, 7, 8), end_date=date(2026, 7, 13))

    budget = BudgetAgent().estimate(_flight(), _hotel(), intent)

    assert budget.inclusive_days == 6
    assert budget.hotel_nights == 5
    # Date-derived per diem: 120 * 6 inclusive days.
    assert budget.per_diem == 720.0
    # The breakdown references the actual trip dates, not literals.
    assert any("2026-07-08 to 2026-07-13" in line for line in budget.breakdown)


def test_single_day_trip_is_valid():
    """Same start/end => 1 inclusive day, 0 nights (boundary, still valid)."""
    intent = TripIntent(start_date=date(2026, 7, 8), end_date=date(2026, 7, 8))

    budget = BudgetAgent().estimate(_flight(), _hotel(nights=0), intent)

    assert budget.inclusive_days == 1
    assert budget.hotel_nights == 0


def test_invalid_dates_raise():
    """end_date before start_date is rejected."""
    intent = TripIntent(start_date=date(2026, 7, 13), end_date=date(2026, 7, 8))

    with pytest.raises(ValueError):
        BudgetAgent().estimate(_flight(), _hotel(), intent)
