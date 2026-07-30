"""Tests for the ConversationalPlanningAgent multi-turn flow (offline)."""

from __future__ import annotations

from app.agents.conversational_planning_agent import ConversationalPlanningAgent
from app.repositories.trip_repository import TripRepository
from app.schemas.trip import TripPhase


def test_multi_turn_planning_example():
    repo = TripRepository()
    agent = ConversationalPlanningAgent(trip_repository=repo)

    # A purpose is provided so the trip can clear policy and reach approval.
    t1 = agent.handle("Preciso viajar para uma reunião.")
    assert t1.requires_clarification is True
    assert "destino" in t1.reply.lower()
    trip_id = t1.trip_id

    t2 = agent.handle("San Jose.")
    assert t2.trip_id == trip_id                 # same trip
    assert t2.requires_clarification is True
    assert "SJC" in t2.reply and "SJO" in t2.reply  # ambiguity question

    t3 = agent.handle("California.")
    assert t3.trip_id == trip_id
    assert t3.requires_clarification is True
    assert "datas" in t3.reply.lower()           # now asks for dates

    t4 = agent.handle("29/06 a 10/07.")
    assert t4.trip_id == trip_id
    assert t4.requires_clarification is False
    assert t4.reply.startswith("Entendido")
    assert t4.phase == TripPhase.AWAITING_APPROVAL.value

    # Only ONE trip ever created; intent fully resolved.
    assert len(repo.list()) == 1
    run = repo.get(trip_id)
    assert run.intent.destination.airport == "SJC"
    assert str(run.intent.start_date) == "2026-06-29"
    assert str(run.intent.end_date) == "2026-07-10"


def test_trip_id_preserved_and_no_new_trip_during_clarification():
    repo = TripRepository()
    agent = ConversationalPlanningAgent(trip_repository=repo)

    first = agent.handle("Quero planejar uma viagem.")
    tid = first.trip_id
    # Several clarification answers — all must stay on the same trip.
    agent.handle("Belo Horizonte.")
    agent.handle("08/06 a 13/06.")
    assert agent.active_trip_id == tid
    assert all(r.id == tid for r in repo.list())
    assert len(repo.list()) == 1


def test_single_full_message_resolves_in_one_turn():
    # Domestic route (under budget) → resolves and reaches approval in one turn.
    agent = ConversationalPlanningAgent()
    turn = agent.handle(
        "Preciso viajar de Goiânia para Belo Horizonte entre 08 e 13 de junho "
        "para reuniões do EnergyGPT."
    )
    assert turn.requires_clarification is False
    assert turn.reply.startswith("Entendido")
    assert turn.phase == TripPhase.AWAITING_APPROVAL.value


def test_new_trip_after_completion_uses_new_id():
    repo = TripRepository()
    agent = ConversationalPlanningAgent(trip_repository=repo)
    a = agent.handle("Viagem para Belo Horizonte de 08/06 a 13/06.")
    first_id = a.trip_id
    # Force the first trip to a terminal state, then a new message starts fresh.
    run = repo.get(first_id)
    run.phase = TripPhase.COMPLETED
    repo.save(run)
    b = agent.handle("Agora quero ir para São Paulo de 01/09 a 05/09.")
    assert b.trip_id != first_id
    assert len(repo.list()) == 2
