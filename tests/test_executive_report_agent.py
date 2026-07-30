"""Tests for ExecutiveReportAgent (Gemini Pro mocked; deterministic fallback)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.agents.executive_report_agent import ExecutiveReportAgent
from app.schemas.approval import ApprovalDecision, ApprovalResult, ApprovalStatus
from app.schemas.budget import BudgetEstimate
from app.schemas.flight import FlightOption
from app.schemas.hotel import HotelOption
from app.schemas.policy import Finding, PolicyResult
from app.schemas.trip import Location, TripIntent

_REQUIRED_SECTIONS = [
    "# Executive Travel Recommendation",
    "## Purpose",
    "## Recommended Itinerary",
    "## Cost Summary",
    "## Policy Compliance",
    "## Approval Status",
    "## Final Recommendation",
]


def _fixtures():
    intent = TripIntent(
        origin=Location(city="Curitiba", airport="CWB", country="Brazil"),
        destination=Location(city="San Jose", airport="SJC", region="California", country="United States"),
        start_date=date(2026, 6, 29), end_date=date(2026, 7, 10),
        purpose="participar do evento AI Engineering da Anthropic",
        event_name="AI Engineering", organization="Anthropic",
    )
    flight = FlightOption(
        id="f1", provider="google_flights", airline="Azul", flight_number="AD-4110",
        origin_airport="CWB", destination_airport="SJC",
        departure_time="2026-06-29T11:20:00", arrival_time="2026-06-29T20:00:00",
        duration_minutes=520, stops=0, price=455.50, currency="BRL",
    )
    hotel = HotelOption(
        id="h1", provider="hotel_sim", hotel_name="Quality Hotel San Jose",
        chain="Quality", stars=4.0, distance_km=2.1, nightly_rate=320.0,
        nights=11, total_price=3520.0, currency="BRL",
    )
    budget = BudgetEstimate(
        flight_cost=455.50, hotel_cost=3520.0, per_diem=1440.0, local_transport=300.0,
        contingency=571.55, total=6287.05, currency="BRL", inclusive_days=12, hotel_nights=11,
    )
    policy = PolicyResult(
        status="pass",
        findings=[Finding(rule_id="R1", severity="pass", message="Trip purpose is present.")],
        requires_human_approval=True,
    )
    approval = ApprovalResult(
        status=ApprovalStatus.APPROVED, requires_human_approval=True,
        decision=ApprovalDecision(
            decision="approved", reviewer="maria.gestora", comments="Aprovado para o evento",
            timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
    )
    return intent, flight, hotel, budget, policy, approval


def test_deterministic_report_has_all_sections_and_data():
    intent, flight, hotel, budget, policy, approval = _fixtures()
    md = ExecutiveReportAgent(use_llm=False).build_report(
        intent=intent, flight=flight, hotel=hotel, budget=budget, policy=policy, approval=approval
    )
    for section in _REQUIRED_SECTIONS:
        assert section in md, section
    assert "Azul AD-4110" in md
    assert "Quality Hotel San Jose" in md
    assert "6287.05 BRL" in md
    assert "maria.gestora" in md
    assert "PASS" in md
    assert "Recomendado e aprovado" in md


def test_blocked_policy_yields_not_recommended():
    intent, flight, hotel, budget, _policy, approval = _fixtures()
    blocked = PolicyResult(
        status="block",
        findings=[Finding(rule_id="R2", severity="block", message="Over the hard budget limit.")],
        requires_human_approval=True,
    )
    md = ExecutiveReportAgent(use_llm=False).build_report(
        intent=intent, flight=flight, hotel=hotel, budget=budget, policy=blocked, approval=approval
    )
    assert "Não recomendado" in md


def test_gemini_pro_markdown_used_when_enabled():
    intent, flight, hotel, budget, policy, approval = _fixtures()
    fake_md = "# Executive Travel Recommendation\n## Purpose\nGerado pelo Gemini Pro."
    agent = ExecutiveReportAgent(generate=lambda _p: fake_md, use_llm=True)
    md = agent.build_report(
        intent=intent, flight=flight, hotel=hotel, budget=budget, policy=policy, approval=approval
    )
    assert md == fake_md


def test_gemini_failure_falls_back_to_deterministic():
    intent, flight, hotel, budget, policy, approval = _fixtures()

    def _raise(_prompt):
        raise RuntimeError("gemini pro unavailable")

    md = ExecutiveReportAgent(generate=_raise, use_llm=True).build_report(
        intent=intent, flight=flight, hotel=hotel, budget=budget, policy=policy, approval=approval
    )
    assert "# Executive Travel Recommendation" in md
    assert "6287.05 BRL" in md  # deterministic content present


def test_prompt_lists_required_sections():
    from app.llm.prompts import build_executive_report_prompt

    prompt = build_executive_report_prompt("FATOS")
    for section in _REQUIRED_SECTIONS:
        assert section in prompt
