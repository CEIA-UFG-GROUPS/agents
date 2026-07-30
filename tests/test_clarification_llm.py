"""Tests for LLM-backed clarification replies and the rejection terminal phase.

The LLM is disabled suite-wide (see conftest), so the model call is faked by
injecting `generate` — no real Gemini traffic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from app.agents.intent_understanding_agent import IntentUnderstandingAgent
from app.agents.travel_planner import location_from_answer
from app.orchestrator.orchestrator import Orchestrator
from app.repositories.trip_repository import TripRepository
from app.schemas.trip import TripPhase, TripRun


def _fake_generate(payload: dict):
    """Return a generate() that always answers with `payload` as JSON."""
    return lambda _prompt: json.dumps(payload)


def _new_run(repo: TripRepository, text: str) -> TripRun:
    run = TripRun(
        id=str(uuid4()),
        request_text=text,
        phase=TripPhase.CREATED,
        created_at=datetime.now(timezone.utc),
    )
    return repo.add(run)


# --- bare answers, understood only via the LLM ----------------------------- #
def test_interpret_clarification_reads_a_bare_airport_code():
    agent = IntentUnderstandingAgent(generate=_fake_generate({"origin_text": "GRU"}))
    extraction = agent.interpret_clarification("GRU", question="Qual é o aeroporto de origem?")
    assert extraction.origin_text == "GRU"
    assert location_from_answer(extraction.origin_text).airport == "GRU"


def test_interpret_clarification_reads_a_bare_date_range():
    agent = IntentUnderstandingAgent(
        generate=_fake_generate({"start_date": "2026-09-10", "end_date": "2026-09-15"})
    )
    extraction = agent.interpret_clarification("10 a 15 de setembro", question="Quais as datas?")
    assert str(extraction.start_date) == "2026-09-10"
    assert str(extraction.end_date) == "2026-09-15"


def test_clarification_question_routes_a_bare_city_to_the_origin():
    """A lone city answers whichever field was asked — the regex parser cannot."""
    agent = IntentUnderstandingAgent(generate=_fake_generate({"origin_text": "Recife"}))
    extraction = agent.interpret_clarification("Recife", question="De onde você parte?")
    assert extraction.origin_text == "Recife"
    assert extraction.destination_text is None


# --- explicit IATA codes in a city answer ---------------------------------- #
def test_location_from_answer_keeps_a_spelled_out_code():
    location = location_from_answer("São Paulo (GRU)")
    assert location.airport == "GRU"
    assert location.city == "São Paulo"


def test_location_from_answer_falls_back_to_a_plain_mention():
    assert location_from_answer("Belo Horizonte").city == "Belo Horizonte"
    assert location_from_answer("Belo Horizonte").airport is None


# --- deterministic fallback ------------------------------------------------ #
def test_clarification_falls_back_to_the_regex_parser_when_llm_is_off():
    repo = TripRepository()
    orch = Orchestrator(trip_repository=repo)
    run = _new_run(repo, "Preciso planejar uma viagem corporativa para Lisboa para reuniões.")
    orch.run_until_stop(run)

    orch.clarify(run, "o destino é Belo Horizonte, de 10-08-2026 a 15-08-2026")

    assert run.intent.destination.airport == "CNF"
    assert str(run.intent.start_date) == "2026-08-10"


# --- rejection is terminal ------------------------------------------------- #
def test_rejection_moves_the_run_to_the_terminal_phase():
    repo = TripRepository()
    orch = Orchestrator(trip_repository=repo)
    run = _new_run(
        repo,
        "Preciso planejar uma viagem corporativa para Belo Horizonte "
        "entre 08 e 13 de junho para reuniões.",
    )
    orch.run_until_stop(run)
    assert run.phase is TripPhase.AWAITING_APPROVAL

    orch.reject(run, reviewer="gestor", comments="fora do orçamento")

    assert run.phase is TripPhase.REJECTED
    summary = orch.run_until_stop(run)
    assert summary.stop_reason == "rejected"
    assert run.phase is TripPhase.REJECTED
