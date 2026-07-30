"""Tests for the ClarificationAgent (Gemini phrasing mocked)."""

from __future__ import annotations

from app.agents.clarification_agent import ClarificationAgent
from app.schemas.location import AirportOption

_SAN_JOSE_OPTIONS = [
    AirportOption(airport="SJC", city="San Jose", region="California", country="United States"),
    AirportOption(airport="SJO", city="San José", region=None, country="Costa Rica"),
]


def _offline_agent() -> ClarificationAgent:
    return ClarificationAgent(use_llm=False)


def test_nothing_missing_no_clarification():
    res = _offline_agent().clarify(missing=[], ambiguous=None)
    assert res.requires_clarification is False
    assert res.question is None


def test_missing_destination_question():
    res = _offline_agent().clarify(missing=["destination_airport"])
    assert res.requires_clarification is True
    assert res.question == "Qual é o destino da viagem?"


def test_missing_dates_question():
    res = _offline_agent().clarify(missing=["start_date", "end_date"])
    assert res.question == "Quais são as datas de ida e volta?"


def test_ambiguous_destination_lists_options():
    res = _offline_agent().clarify(missing=["destination_airport"], ambiguous=("destination", _SAN_JOSE_OPTIONS))
    assert res.requires_clarification is True
    assert res.question == (
        "Você deseja viajar para San Jose, California (SJC) ou "
        "San José, Costa Rica (SJO)?"
    )


def test_multiple_missing_lists_all():
    res = _offline_agent().clarify(missing=["destination_airport", "start_date", "end_date"])
    assert "aeroporto de destino" in res.question
    assert "data de ida" in res.question and "data de volta" in res.question


def test_gemini_phrases_question_when_enabled():
    agent = ClarificationAgent(
        generate=lambda _p: "Para onde vamos viajar? 🙂", use_llm=True
    )
    res = agent.clarify(missing=["destination_airport"])
    assert res.requires_clarification is True
    assert res.question == "Para onde vamos viajar? 🙂"  # Gemini wording used


def test_gemini_failure_falls_back_to_deterministic():
    def _raise(_prompt):
        raise RuntimeError("gemini error")

    agent = ClarificationAgent(generate=_raise, use_llm=True)
    res = agent.clarify(missing=["start_date", "end_date"])
    assert res.question == "Quais são as datas de ida e volta?"  # fallback
