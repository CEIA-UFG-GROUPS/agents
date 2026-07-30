"""Tests for provider-based airport resolution."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.orchestrator.orchestrator import Orchestrator
from app.repositories.trip_repository import TripRepository
from app.schemas.location import LocationQuery, ResolvedLocation
from app.tools.location_resolver_tool import LocationResolverTool
from app.tools.providers.location_resolver_provider import LocationResolverProvider
from app.tools.providers.offline_demo_location_resolver_provider import (
    OfflineDemoLocationResolverProvider,
)
from app.schemas.trip import TripPhase, TripRun


def test_offline_resolves_known_city():
    res = OfflineDemoLocationResolverProvider().resolve(LocationQuery(city="Curitiba"))
    assert res.airport == "CWB"
    assert res.country == "Brazil"
    assert res.confidence >= 0.80
    assert res.requires_clarification is False


def test_san_jose_with_region_resolves_to_sjc_usa():
    res = LocationResolverTool().resolve(
        LocationQuery(city="San Jose", region="California")
    )
    assert res.airport == "SJC"
    assert res.country == "United States"
    assert res.requires_clarification is False


def test_san_jose_ambiguous_requires_clarification_with_options():
    res = LocationResolverTool().resolve(LocationQuery(city="San Jose"))
    assert res.requires_clarification is True
    assert {o.airport for o in res.options} == {"SJC", "SJO"}


def test_unknown_city_requires_clarification():
    res = LocationResolverTool().resolve(LocationQuery(city="Atlantis"))
    assert res.requires_clarification is True
    assert res.airport is None


def test_tool_validates_iata_and_confidence():
    class BadProvider(LocationResolverProvider):
        name = "bad"

        def resolve(self, query: LocationQuery) -> ResolvedLocation:
            # 4 letters + low confidence — must be rejected by the tool.
            return ResolvedLocation(airport="ABCD", confidence=0.4)

    res = LocationResolverTool(provider=BadProvider()).resolve(LocationQuery(city="X"))
    assert res.requires_clarification is True


def test_pipeline_curitiba_to_san_jose_california():
    repo = TripRepository()
    orch = Orchestrator(trip_repository=repo)
    run = TripRun(
        id=str(uuid4()),
        request_text=(
            "Preciso planejar uma viagem corporativa de Curitiba para San Jose, "
            "Califórnia, entre 29 de junho de 2026 e 10 de julho de 2026 para "
            "participar do evento AI Engineering da Anthropic."
        ),
        phase=TripPhase.CREATED,
        created_at=datetime.now(timezone.utc),
    )
    repo.add(run)
    orch.run_until_stop(run)

    assert run.requires_clarification is False
    assert run.intent.origin.airport == "CWB"
    assert run.intent.destination.airport == "SJC"
    assert run.intent.destination.country == "United States"
    step_names = [s.name for s in run.steps]
    assert "resolve_locations" in step_names
    assert "search_flights" in step_names
    assert run.flight_options[0].origin_airport == "CWB"
    assert run.flight_options[0].destination_airport == "SJC"


def test_pipeline_ambiguous_san_jose_stops_for_clarification():
    repo = TripRepository()
    orch = Orchestrator(trip_repository=repo)
    run = TripRun(
        id=str(uuid4()),
        request_text=(
            "Preciso planejar uma viagem corporativa de Curitiba para San Jose "
            "entre 29 de junho de 2026 e 10 de julho de 2026 para reuniões."
        ),
        phase=TripPhase.CREATED,
        created_at=datetime.now(timezone.utc),
    )
    repo.add(run)
    summary = orch.run_until_stop(run)

    assert summary.stop_reason == "clarification_required"
    assert run.phase is TripPhase.RESOLVING_LOCATIONS
    assert run.intent.destination.airport is None
    # Ambiguity options surfaced in the question.
    assert "SJC" in run.clarification_question and "SJO" in run.clarification_question
