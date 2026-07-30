"""Simulated hotel provider — deterministic, offline data for the demo.

Returns a fixed set of 5 hotels for the requested destination/stay, with hotel
names and addresses generated from the destination city (no hardcoded city).
Deterministic so the demo is reproducible. Swap for a real HotelProvider later
behind the same interface.
"""

from __future__ import annotations

from app.schemas.hotel import HotelOption, HotelSearchInput
from app.tools.providers.hotel_provider import HotelProvider

# Deterministic catalog template — independent of the destination city. The
# {city} placeholder is filled per request. Includes two "Quality" chain hotels
# so the traveler's preferred-chain memory is represented.
_HOTEL_TEMPLATES: list[dict] = [
    {"name": "Quality Hotel {city}",   "chain": "Quality",  "stars": 4.0, "distance_km": 2.1, "nightly_rate": 320.00, "area": "Centro"},
    {"name": "Mercure {city} Centro",  "chain": "Accor",    "stars": 4.0, "distance_km": 1.5, "nightly_rate": 410.00, "area": "Centro"},
    {"name": "Ibis {city} Aeroporto",  "chain": "Accor",    "stars": 3.0, "distance_km": 0.9, "nightly_rate": 240.00, "area": "Aeroporto"},
    {"name": "Radisson {city} Plaza",  "chain": "Radisson", "stars": 5.0, "distance_km": 3.2, "nightly_rate": 560.00, "area": "Zona Sul"},
    {"name": "Quality Suites {city}",  "chain": "Quality",  "stars": 4.0, "distance_km": 4.0, "nightly_rate": 350.00, "area": "Zona Sul"},
]


class SimulatedHotelProvider(HotelProvider):
    """Returns 5 deterministic hotels for the query. No network calls."""

    def __init__(self, name: str = "hotel_sim") -> None:
        self.name = name

    def search(self, query: HotelSearchInput) -> list[HotelOption]:
        nights = max((query.check_out - query.check_in).days, 1)
        city = query.destination
        slug = city.lower().replace(" ", "-")
        options: list[HotelOption] = []
        for i, tmpl in enumerate(_HOTEL_TEMPLATES, start=1):
            options.append(
                HotelOption(
                    id=f"{self.name}-{slug}-{i:02d}",
                    provider=self.name,
                    hotel_name=tmpl["name"].format(city=city),
                    chain=tmpl["chain"],
                    address=f"{tmpl['area']}, {city}",
                    stars=tmpl["stars"],
                    distance_km=tmpl["distance_km"],
                    nightly_rate=tmpl["nightly_rate"],
                    nights=nights,
                    total_price=round(tmpl["nightly_rate"] * nights, 2),
                    currency="BRL",
                    simulated=True,
                )
            )
        return options
