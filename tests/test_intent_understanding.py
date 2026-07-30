"""Tests for the Gemini-powered IntentUnderstandingAgent (Gemini mocked)."""

from __future__ import annotations

from app.agents.intent_understanding_agent import IntentUnderstandingAgent
from app.llm.prompts import build_intent_prompt

# --- mocked Gemini replies ------------------------------------------------- #
_FULL_JSON = """{
  "origin_text": "Curitiba",
  "destination_text": "San Jose, California",
  "start_date": "2026-06-29",
  "end_date": "2026-07-10",
  "purpose": "participar do evento AI Engineering da Anthropic",
  "event_name": "AI Engineering",
  "organization": "Anthropic",
  "missing_fields": [],
  "confidence": 0.95
}"""

_PARTIAL_JSON = """```json
{
  "origin_text": "...",
  "destination_text": "San Jose",
  "start_date": "",
  "end_date": "",
  "purpose": "ir para San Jose",
  "event_name": "...",
  "organization": "...",
  "missing_fields": ["origin", "start_date", "end_date"],
  "confidence": 0.5
}
```"""


def test_prompt_contains_request_and_json_contract():
    prompt = build_intent_prompt("viagem para San Jose")
    assert "REQUEST: viagem para San Jose" in prompt
    assert '"missing_fields"' in prompt and '"event_name"' in prompt
    assert "assume 2026" in prompt


def test_gemini_full_extraction_curitiba_to_san_jose():
    agent = IntentUnderstandingAgent(generate=lambda _p: _FULL_JSON, use_llm=True)
    intent = agent.understand(
        "Preciso planejar uma viagem corporativa de Curitiba para San Jose, "
        "Califórnia, entre 29 de junho de 2026 e 10 de julho de 2026 para "
        "participar do evento AI Engineering da Anthropic."
    )
    assert intent.origin.city == "Curitiba"
    assert intent.origin.airport is None  # not resolved here
    assert intent.destination.city == "San Jose"
    assert intent.destination.region == "California"
    assert intent.destination.airport is None
    assert str(intent.start_date) == "2026-06-29"
    assert str(intent.end_date) == "2026-07-10"
    assert intent.event_name == "AI Engineering"
    assert intent.organization == "Anthropic"


def test_gemini_partial_missing_dates_and_bare_destination():
    agent = IntentUnderstandingAgent(generate=lambda _p: _PARTIAL_JSON, use_llm=True)
    intent = agent.understand("Preciso ir para San Jose")
    assert intent.destination.city == "San Jose"
    assert intent.destination.region is None  # ambiguous downstream
    assert intent.origin is None              # "..." cleaned to None
    assert intent.start_date is None
    assert intent.end_date is None


def test_llm_disabled_uses_deterministic_parser():
    # use_llm=False → never calls the (failing) generate; uses the parser.
    def _boom(_prompt):  # pragma: no cover - must not be called
        raise AssertionError("LLM must not be called when disabled")

    agent = IntentUnderstandingAgent(generate=_boom, use_llm=False)
    intent = agent.understand(
        "Preciso planejar uma viagem corporativa para Belo Horizonte entre 08 e "
        "13 de junho para reuniões do EnergyGPT."
    )
    assert intent.destination.city == "Belo Horizonte"
    assert str(intent.start_date) == "2026-06-08"
    assert str(intent.end_date) == "2026-06-13"


def test_gemini_failure_falls_back_to_deterministic():
    def _raise(_prompt):
        raise RuntimeError("gemini 404 / network error")

    agent = IntentUnderstandingAgent(generate=_raise, use_llm=True)
    intent = agent.understand(
        "Preciso viajar de Curitiba para Belo Horizonte entre 08 e 13 de junho "
        "para reuniões."
    )
    # Fallback parser still produced a usable intent.
    assert intent.origin.city == "Curitiba"
    assert intent.destination.city == "Belo Horizonte"
    assert str(intent.start_date) == "2026-06-08"
