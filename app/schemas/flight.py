"""Flight search schemas (provider-agnostic).

The same input/output shape is used by both google_flights_tool and
skyscanner_tool so providers are swappable. See specs/tools.md.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class FlightSearchInput(BaseModel):
    """Provider-agnostic flight query."""

    origin: str
    destination: str
    depart_date: date
    return_date: Optional[date] = None
    passengers: int = 1
    cabin: Optional[str] = "economy"
    # Countries let the provider detect international routes (realistic data).
    origin_country: Optional[str] = None
    destination_country: Optional[str] = None


class FlightOption(BaseModel):
    """A single candidate flight returned by a flight provider."""

    id: str
    provider: str
    # Which tool surfaced this option (e.g. "google_flights_tool"); stamped by
    # the tool itself for observability. Default "" until a tool sets it.
    source_tool: str = ""
    airline: str
    flight_number: str
    origin_airport: str
    destination_airport: str
    departure_time: str
    arrival_time: str
    duration_minutes: int
    stops: int = 0
    price: float = 0.0
    currency: str = "BRL"
    # Whether the traveler's preferred seat type can be booked on this flight.
    preferred_seat_available: bool = False
    simulated: bool = True


class FlightSearchResult(BaseModel):
    """Result wrapper returned by the flight tools."""

    options: list[FlightOption] = Field(default_factory=list)
