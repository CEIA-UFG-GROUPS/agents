"""Tests for route-aware simulated flight generation (domestic vs international)."""

from __future__ import annotations

from datetime import date

from app.agents.flight_ranking_agent import FlightRankingAgent
from app.schemas.flight import FlightSearchInput
from app.tools.providers.simulated_flight_provider import SimulatedFlightProvider


def _domestic_query() -> FlightSearchInput:
    return FlightSearchInput(
        origin="GYN", destination="CNF", depart_date=date(2026, 6, 8),
        origin_country="Brazil", destination_country="Brazil",
    )


def _international_query() -> FlightSearchInput:
    return FlightSearchInput(
        origin="CWB", destination="SJC", depart_date=date(2026, 6, 29),
        origin_country="Brazil", destination_country="United States",
    )


def test_domestic_keeps_short_nonstop_options():
    options = SimulatedFlightProvider().search(_domestic_query())
    assert len(options) == 5
    assert all(o.duration_minutes <= 200 for o in options)
    assert any(o.stops == 0 for o in options)
    assert all(o.price < 1000 for o in options)


def test_international_generates_long_haul_options():
    options = SimulatedFlightProvider().search(_international_query())
    assert len(options) == 5
    # No direct flights; realistic durations and prices.
    assert all(o.stops >= 1 for o in options)
    assert all(900 <= o.duration_minutes <= 1500 for o in options)
    assert all(4500 <= o.price <= 9000 for o in options)
    airlines = {o.airline for o in options}
    assert "Copa" in airlines and "United" in airlines and "Delta" in airlines
    assert any("American" in a for a in airlines)


def test_international_arrival_can_be_next_day():
    options = SimulatedFlightProvider().search(_international_query())
    # The 22:10 + 980 min option arrives the following day.
    overnight = next(o for o in options if o.departure_time.endswith("T22:10:00"))
    assert overnight.departure_time.startswith("2026-06-29")
    assert overnight.arrival_time.startswith("2026-06-30")


def test_no_country_info_defaults_to_domestic():
    options = SimulatedFlightProvider().search(
        FlightSearchInput(origin="GYN", destination="CNF", depart_date=date(2026, 6, 8))
    )
    assert all(o.duration_minutes <= 200 for o in options)


def test_no_nonstop_dominance_for_international():
    options = SimulatedFlightProvider().search(_international_query())
    ranking = FlightRankingAgent().rank(options, {})
    # Every option has stops, so none gets a "non-stop" reason.
    assert ranking.recommended_flight is not None
    assert all(o.stops >= 1 for o in options)
    assert all("non-stop" not in r.reasons for r in ranking.ranking)


def _intl_option(stops: int, **over):
    base = dict(
        id=f"opt-{stops}-{over.get('price', 0)}", provider="p", airline="X",
        flight_number=str(stops), origin_airport="CWB", destination_airport="SJC",
        departure_time="2026-06-29T08:00:00", arrival_time="2026-06-30T00:00:00",
        duration_minutes=1000, price=5000.0, currency="BRL",
        preferred_seat_available=True,
    )
    base.update(over)
    from app.schemas.flight import FlightOption
    return FlightOption(stops=stops, **base)


def test_fewer_stops_preferred_all_else_equal():
    one_stop = _intl_option(1, id="one")
    two_stop = _intl_option(2, id="two")
    ranking = FlightRankingAgent().rank([two_stop, one_stop], {})
    assert ranking.recommended_flight.id == "one"  # fewer stops wins, all else equal
    assert ranking.ranking[0].flight_id == "one"
