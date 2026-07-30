"""Tests for conversational clarification on an existing TripRun."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.agents.travel_planner import parse_clarification
from app.orchestrator.orchestrator import Orchestrator
from app.repositories.trip_repository import TripRepository
from app.schemas.trip import TripPhase, TripRun


def _new_run(repo: TripRepository, text: str) -> TripRun:
    run = TripRun(
        id=str(uuid4()),
        request_text=text,
        phase=TripPhase.CREATED,
        created_at=datetime.now(timezone.utc),
    )
    return repo.add(run)


def test_vague_message_creates_one_run_requiring_clarification():
    repo = TripRepository()
    orch = Orchestrator(trip_repository=repo)
    # Unknown destination airport + no dates.
    run = _new_run(repo, "Preciso planejar uma viagem corporativa para Lisboa para reuniões.")
    orch.run_until_stop(run)
    repo.save(run)

    assert len(repo.list()) == 1
    assert run.requires_clarification is True
    assert run.phase is TripPhase.RESOLVING_LOCATIONS
    assert "aeroporto de destino" in run.clarification_question


def test_clarification_updates_same_trip_and_continues():
    repo = TripRepository()
    orch = Orchestrator(trip_repository=repo)
    run = _new_run(repo, "Preciso planejar uma viagem corporativa para Lisboa para reuniões.")
    orch.run_until_stop(run)
    repo.save(run)
    original_id = run.id
    assert run.requires_clarification is True

    # Reply with only the missing info — must update the SAME run, no new run.
    orch.clarify(run, "o destino é Belo Horizonte, de 10-08-2026 a 15-08-2026")
    repo.save(run)

    assert run.id == original_id
    assert len(repo.list()) == 1                      # no new TripRun created
    assert run.requires_clarification is False
    assert run.clarification_question is None
    assert run.intent.destination.airport == "CNF"
    assert str(run.intent.start_date) == "2026-08-10"
    assert str(run.intent.end_date) == "2026-08-15"

    # The workflow can now continue past RETRIEVING_MEMORY into flight search.
    orch.run_until_stop(run)
    step_names = [s.name for s in run.steps]
    assert "search_flights" in step_names
    assert len(run.flight_options) == 5


def test_clarification_preserves_existing_fields():
    repo = TripRepository()
    orch = Orchestrator(trip_repository=repo)
    # Destination known (Belo Horizonte -> CNF); origin + dates missing.
    run = _new_run(
        repo,
        "Preciso planejar uma viagem corporativa de Goiânia para Belo Horizonte para reuniões.",
    )
    orch.run_until_stop(run)
    repo.save(run)
    assert run.requires_clarification is True  # dates missing

    orch.clarify(run, "ida em 29-06-2026, volta em 10-07-2026")

    # Existing destination/origin preserved; only dates filled.
    assert run.intent.destination.airport == "CNF"
    assert run.intent.origin.airport == "GYN"
    assert str(run.intent.start_date) == "2026-06-29"
    assert str(run.intent.end_date) == "2026-07-10"
    assert run.requires_clarification is False


def test_clarification_parser_partials():
    # The planner extracts text only — airports stay None (resolved later).
    p = parse_clarification("ida em 29-06-2026, volta em 10-07-2026", 2026)
    assert str(p["start_date"]) == "2026-06-29"
    assert str(p["end_date"]) == "2026-07-10"
    assert p["origin"] is None and p["destination"] is None

    p = parse_clarification("o destino é San Jose, Califórnia", 2026)
    assert p["destination"].city == "San Jose"
    assert p["destination"].region == "Califórnia"
    assert p["destination"].airport is None  # not resolved by the parser

    p = parse_clarification("saindo de Curitiba", 2026)
    assert p["origin"].city == "Curitiba"
    assert p["origin"].airport is None

    p = parse_clarification(
        "vou sair de Curitiba para San Jose, Califórnia, de 29-06 a 10-07", 2026
    )
    assert p["origin"].city == "Curitiba"
    assert p["destination"].city == "San Jose"
    assert str(p["start_date"]) == "2026-06-29"
    assert str(p["end_date"]) == "2026-07-10"
