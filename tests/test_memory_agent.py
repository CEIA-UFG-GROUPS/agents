"""Tests for MemoryAgent summarization (deterministic retrieval; Gemini mocked)."""

from __future__ import annotations

from app.agents.memory_agent import MemoryAgent


def test_build_profile_is_deterministic():
    profile = MemoryAgent().build_profile()
    assert profile.preferred_seat == "window"
    assert profile.preferred_hotel_chain == "Quality"
    assert profile.preferred_departure_window == "morning"
    assert profile.previous_destinations == ["Belo Horizonte", "São Paulo", "Rio de Janeiro"]


def test_summary_deterministic_offline():
    summary = MemoryAgent(use_llm=False).summarize()
    p = summary.traveler_profile
    assert p.preferred_seat == "window"
    assert "Quality" in summary.trip_history_summary
    assert "Belo Horizonte" in summary.trip_history_summary
    assert "São Paulo" in summary.trip_history_summary
    assert "manhã" in summary.trip_history_summary


def test_summary_uses_gemini_when_enabled():
    agent = MemoryAgent(
        generate=lambda _p: "Viajante frequente do Sudeste, prefere janela e Quality Hotels.",
        use_llm=True,
    )
    summary = agent.summarize()
    # Profile stays deterministic; only the prose comes from Gemini.
    assert summary.traveler_profile.preferred_hotel_chain == "Quality"
    assert summary.trip_history_summary == (
        "Viajante frequente do Sudeste, prefere janela e Quality Hotels."
    )


def test_summary_falls_back_when_gemini_fails():
    def _raise(_prompt):
        raise RuntimeError("gemini error")

    summary = MemoryAgent(generate=_raise, use_llm=True).summarize()
    assert "Quality" in summary.trip_history_summary  # deterministic fallback


def test_enrich_still_works():
    # Retrieval/enrichment behavior is unchanged by the new summarization.
    from app.schemas.trip import TripIntent

    agent = MemoryAgent()
    result = agent.enrich(TripIntent(), agent.retrieve())
    assert result.intent.origin.city == "São Paulo"
    assert result.intent.origin.airport == "GRU"
