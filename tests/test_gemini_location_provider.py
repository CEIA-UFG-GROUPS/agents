"""Tests for the Gemini location provider + LocationUnderstandingAgent.

Gemini is mocked (a `generate` callable is injected) — no network calls.
"""

from __future__ import annotations

from datetime import date

from app.agents.location_understanding_agent import LocationUnderstandingAgent
from app.llm.prompts import build_location_prompt
from app.schemas.location import LocationQuery
from app.schemas.trip import Location, TripIntent
from app.tools.location_resolver_tool import LocationResolverTool
from app.tools.providers.gemini_location_resolver_provider import (
    GeminiLocationResolverProvider,
)

# --- mocked Gemini replies ------------------------------------------------- #
_SJC_JSON = """{
  "location_text": "San Jose, California", "city": "San Jose",
  "region": "California", "country": "United States",
  "airport": "SJC", "airport_name": "Norman Y. Mineta San José International",
  "confidence": 0.95, "is_ambiguous": false, "alternatives": [], "reason": "clear"
}"""

_CWB_JSON = """{
  "location_text": "Curitiba", "city": "Curitiba", "region": null,
  "country": "Brazil", "airport": "CWB", "airport_name": "Afonso Pena International",
  "confidence": 0.96, "is_ambiguous": false, "alternatives": [], "reason": "clear"
}"""

_AMBIGUOUS_JSON = """```json
{
  "location_text": "San Jose", "city": "San Jose", "region": null, "country": null,
  "airport": null, "airport_name": null, "confidence": 0.4, "is_ambiguous": true,
  "alternatives": [
    {"city": "San Jose", "region": "California", "country": "United States",
     "airport": "SJC", "airport_name": "Norman Y. Mineta San José International"},
    {"city": "San José", "region": null, "country": "Costa Rica",
     "airport": "SJO", "airport_name": "Juan Santamaría International"}
  ],
  "reason": "two well-known San Jose airports"
}
```"""


def _mention(prompt: str) -> str:
    """Extract just the LOCATION_MENTION line (the prompt also carries context)."""
    for line in prompt.splitlines():
        if line.startswith("LOCATION_MENTION:"):
            return line.split(":", 1)[1].strip()
    return ""


def _fake_gemini(prompt: str) -> str:
    """Route by the LOCATION_MENTION (not the surrounding request/intent context)."""
    mention = _mention(prompt)
    if "Curitiba" in mention:
        return _CWB_JSON
    if "California" in mention:
        return _SJC_JSON
    return _AMBIGUOUS_JSON


def _gemini_tool(generate=_fake_gemini) -> LocationResolverTool:
    return LocationResolverTool(provider=GeminiLocationResolverProvider(generate=generate))


# --- provider/tool tests --------------------------------------------------- #
def test_prompt_contains_request_intent_and_json_contract():
    prompt = build_location_prompt(
        LocationQuery(location_text="San Jose", request_text="viagem para San Jose",
                      intent_summary="origin=Curitiba")
    )
    assert "FULL_REQUEST: viagem para San Jose" in prompt
    assert "LOCATION_MENTION: San Jose" in prompt
    assert '"is_ambiguous"' in prompt and '"alternatives"' in prompt


def test_gemini_resolves_san_jose_california():
    res = _gemini_tool().resolve(LocationQuery(city="San Jose", region="California"))
    assert res.airport == "SJC"
    assert res.country == "United States"
    assert res.requires_clarification is False


def test_gemini_markdown_ambiguous_requires_clarification_with_options():
    res = _gemini_tool().resolve(LocationQuery(city="San Jose"))
    assert res.requires_clarification is True
    assert {o.airport for o in res.options} == {"SJC", "SJO"}


def test_tool_rejects_invalid_airport_code():
    bad = '{"airport": "SANJOSE", "confidence": 0.95, "is_ambiguous": false}'
    res = _gemini_tool(generate=lambda _p: bad).resolve(LocationQuery(city="X"))
    assert res.requires_clarification is True


def test_tool_rejects_low_confidence():
    low = '{"airport": "SJC", "confidence": 0.5, "is_ambiguous": false}'
    res = _gemini_tool(generate=lambda _p: low).resolve(LocationQuery(city="San Jose"))
    assert res.requires_clarification is True


# --- agent-level tests (Gemini-backed) ------------------------------------- #
def test_agent_resolves_curitiba_to_san_jose_california():
    agent = LocationUnderstandingAgent(resolver=_gemini_tool())
    intent = TripIntent(
        origin=Location(city="Curitiba"),
        destination=Location(city="San Jose", region="California"),
        start_date=date(2026, 6, 29), end_date=date(2026, 7, 10),
    )
    result = agent.understand("de Curitiba para San Jose, Califórnia", intent)
    assert result.requires_clarification is False
    assert result.intent.origin.airport == "CWB"
    assert result.intent.origin.country == "Brazil"
    assert result.intent.destination.airport == "SJC"
    assert result.intent.destination.country == "United States"


def test_agent_ambiguous_san_jose_builds_clarification_question():
    agent = LocationUnderstandingAgent(resolver=_gemini_tool())
    intent = TripIntent(
        origin=Location(city="Curitiba", airport="CWB"),
        destination=Location(city="San Jose"),
        start_date=date(2026, 6, 29), end_date=date(2026, 7, 10),
    )
    result = agent.understand("viajar para San Jose", intent)
    assert result.requires_clarification is True
    q = result.clarification_question
    assert "San Jose" in q and "SJC" in q and "SJO" in q
    assert q.startswith("Você deseja viajar para")
