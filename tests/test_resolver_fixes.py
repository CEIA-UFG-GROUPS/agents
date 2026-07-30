"""Regression tests: intent extraction + location disambiguation fixes."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.agents.travel_planner import parse_intent_deterministic
from app.orchestrator.orchestrator import Orchestrator
from app.repositories.trip_repository import TripRepository
from app.schemas.location import LocationQuery, ResolvedLocation
from app.tools.location_resolver_tool import LocationResolverTool
from app.tools.providers.location_resolver_provider import LocationResolverProvider
from app.schemas.trip import TripPhase, TripRun

_FULL_REQUEST = (
    "Preciso planejar uma viagem corporativa de Curitiba para San Jose, "
    "Califórnia, entre 29 de junho de 2026 e 10 de julho de 2026 para "
    "participar do evento AI Engineering da Anthropic."
)


def _new_run(repo: TripRepository, text: str) -> TripRun:
    return repo.add(
        TripRun(id=str(uuid4()), request_text=text, phase=TripPhase.CREATED,
                created_at=datetime.now(timezone.utc))
    )


# --- disambiguation -------------------------------------------------------- #
def test_region_qualifier_disambiguates_san_jose():
    tool = LocationResolverTool()
    for q in (
        LocationQuery(city="San Jose", region="Califórnia"),
        LocationQuery(city="San Jose", region="California"),
        LocationQuery(city="San Jose CA"),
        LocationQuery(city="San Jose, Califórnia"),
    ):
        res = tool.resolve(q)
        assert res.airport == "SJC", q
        assert res.requires_clarification is False, q
        assert res.country == "United States"


def test_san_jose_alone_is_ambiguous():
    res = LocationResolverTool().resolve(LocationQuery(city="San Jose"))
    assert res.requires_clarification is True
    assert res.airport is None
    assert {o.airport for o in res.options} == {"SJC", "SJO"}


def test_tool_falls_back_to_offline_when_primary_errors():
    class Boom(LocationResolverProvider):
        name = "gemini"

        def resolve(self, query: LocationQuery) -> ResolvedLocation:
            raise RuntimeError("gemini 404")

    res = LocationResolverTool(provider=Boom()).resolve(
        LocationQuery(city="San Jose", region="California")
    )
    assert res.airport == "SJC"
    assert res.requires_clarification is False


# --- deterministic intent extraction --------------------------------------- #
def test_deterministic_extracts_dates_purpose_event_org():
    intent = parse_intent_deterministic(_FULL_REQUEST, 2026)
    assert intent.origin.city == "Curitiba"
    assert intent.destination.city == "San Jose"
    assert intent.destination.region == "Califórnia"
    assert str(intent.start_date) == "2026-06-29"
    assert str(intent.end_date) == "2026-07-10"
    assert "AI Engineering" in intent.purpose
    assert intent.event_name == "AI Engineering"
    assert intent.organization == "Anthropic"


# --- full pipeline --------------------------------------------------------- #
def test_full_request_continues_past_resolving_locations():
    repo = TripRepository()
    orch = Orchestrator(trip_repository=repo)
    run = _new_run(repo, _FULL_REQUEST)
    summary = orch.run_until_stop(run)

    # It must continue PAST resolution (not get stuck on clarification). The
    # international route legitimately reaches policy (high price → block).
    assert run.requires_clarification is False
    assert summary.stop_reason != "clarification_required"
    assert run.intent.origin.airport == "CWB"
    assert run.intent.destination.airport == "SJC"
    assert run.intent.destination.country == "United States"
    assert run.intent.event_name == "AI Engineering"
    assert run.intent.organization == "Anthropic"
    assert "search_flights" in [s.name for s in run.steps]


def test_ambiguous_request_asks_clarification():
    repo = TripRepository()
    orch = Orchestrator(trip_repository=repo)
    run = _new_run(repo, "Preciso viajar para San Jose.")
    summary = orch.run_until_stop(run)

    assert summary.stop_reason == "clarification_required"
    assert run.phase is TripPhase.RESOLVING_LOCATIONS
    assert run.intent.destination.airport is None
    assert "SJC" in run.clarification_question and "SJO" in run.clarification_question
