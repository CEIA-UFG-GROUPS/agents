"""Simulated flight provider — deterministic, offline data for the demo.

Route-aware: domestic routes (same country) get short, mostly non-stop options;
international routes (origin.country != destination.country) get realistic
long-haul options with 1-2 stops, long durations and higher prices. Deterministic
so the demo is reproducible. Swap for a real provider later behind the interface.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.schemas.flight import FlightOption, FlightSearchInput
from app.tools.providers.flight_provider import FlightProvider

# Domestic schedule (short, mostly non-stop). Each provider tags its options
# with its own name so the FlightSearchAgent can slice from each source.
_DOMESTIC_TEMPLATES: list[dict] = [
    {"airline": "GOL",   "flight_number": "G3-1402", "dep": "06:10", "arr": "07:25", "duration_minutes": 75,  "stops": 0, "price": 512.90, "preferred_seat_available": True},
    {"airline": "LATAM", "flight_number": "LA-3221", "dep": "08:40", "arr": "09:55", "duration_minutes": 75,  "stops": 0, "price": 489.00, "preferred_seat_available": False},
    {"airline": "Azul",  "flight_number": "AD-4110", "dep": "11:20", "arr": "12:45", "duration_minutes": 85,  "stops": 0, "price": 455.50, "preferred_seat_available": True},
    {"airline": "GOL",   "flight_number": "G3-1588", "dep": "15:05", "arr": "17:40", "duration_minutes": 155, "stops": 1, "price": 398.70, "preferred_seat_available": False},
    {"airline": "LATAM", "flight_number": "LA-3990", "dep": "19:30", "arr": "20:50", "duration_minutes": 80,  "stops": 0, "price": 545.00, "preferred_seat_available": True},
]

# International long-haul schedule (1-2 stops, long durations, higher prices,
# arrival computed from departure + duration so it may roll to the next day).
_INTERNATIONAL_TEMPLATES: list[dict] = [
    {"airline": "LATAM + American", "flight_number": "LA-8021/AA-930", "dep": "22:10", "duration_minutes": 980,  "stops": 1, "price": 6200.00, "preferred_seat_available": True},
    {"airline": "Copa",            "flight_number": "CM-415",         "dep": "23:40", "duration_minutes": 1120, "stops": 1, "price": 5400.00, "preferred_seat_available": False},
    {"airline": "United",          "flight_number": "UA-849",         "dep": "06:30", "duration_minutes": 1280, "stops": 2, "price": 4800.00, "preferred_seat_available": True},
    {"airline": "LATAM",           "flight_number": "LA-8042",        "dep": "08:15", "duration_minutes": 1350, "stops": 2, "price": 4500.00, "preferred_seat_available": False},
    {"airline": "Delta",           "flight_number": "DL-110",         "dep": "19:50", "duration_minutes": 1450, "stops": 2, "price": 7000.00, "preferred_seat_available": True},
]


class SimulatedFlightProvider(FlightProvider):
    """Returns 5 deterministic flights for the query. No network calls."""

    def __init__(self, name: str = "google_flights") -> None:
        self.name = name

    def search(self, query: FlightSearchInput) -> list[FlightOption]:
        date_str = str(query.depart_date)
        international = _is_international(query)
        templates = _INTERNATIONAL_TEMPLATES if international else _DOMESTIC_TEMPLATES

        options: list[FlightOption] = []
        for i, tmpl in enumerate(templates, start=1):
            departure_time = f"{date_str}T{tmpl['dep']}:00"
            if tmpl.get("arr"):
                arrival_time = f"{date_str}T{tmpl['arr']}:00"
            else:
                arrival_time = _arrival(departure_time, tmpl["duration_minutes"])
            options.append(
                FlightOption(
                    id=f"{self.name}-{query.origin}-{query.destination}-{date_str}-{i:02d}",
                    provider=self.name,
                    airline=tmpl["airline"],
                    flight_number=tmpl["flight_number"],
                    origin_airport=query.origin,
                    destination_airport=query.destination,
                    departure_time=departure_time,
                    arrival_time=arrival_time,
                    duration_minutes=tmpl["duration_minutes"],
                    stops=tmpl["stops"],
                    price=tmpl["price"],
                    currency="BRL",
                    preferred_seat_available=tmpl["preferred_seat_available"],
                    simulated=True,
                )
            )
        return options


def _is_international(query: FlightSearchInput) -> bool:
    """International when both countries are known and differ."""
    return bool(
        query.origin_country
        and query.destination_country
        and query.origin_country.strip().lower() != query.destination_country.strip().lower()
    )


def _arrival(departure_iso: str, duration_minutes: int) -> str:
    """Arrival ISO timestamp = departure + duration (may roll to the next day)."""
    dep = datetime.fromisoformat(departure_iso)
    return (dep + timedelta(minutes=duration_minutes)).isoformat()
