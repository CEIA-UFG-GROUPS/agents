"""ExecutiveReportAgent — generates an executive travel report (Markdown).

Uses Gemini **Pro** (GEMINI_ADVANCED_MODEL) for the prose when LLM_ENABLED=true,
with a deterministic Markdown fallback when the LLM is off or fails. The facts
come only from the selected flight/hotel/budget/policy/approval. See specs/agents.md.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from app.agents.base import Agent, RunContext
from app.core.config import Settings, get_settings
from app.llm.gemini_client import build_gemini_client
from app.llm.prompts import build_executive_report_prompt
from app.schemas.approval import ApprovalResult
from app.schemas.budget import BudgetEstimate
from app.schemas.flight import FlightOption
from app.schemas.hotel import HotelOption
from app.schemas.policy import PolicyResult
from app.schemas.trip import TripIntent

logger = logging.getLogger("app.agents.executive_report")


class ExecutiveReportAgent(Agent):
    """Produces a Markdown executive travel recommendation."""

    name = "ExecutiveReportAgent"

    def __init__(
        self,
        generate: Optional[Callable[[str], str]] = None,
        use_llm: Optional[bool] = None,
    ) -> None:
        self._generate = generate  # inject for tests
        self._use_llm = use_llm  # override settings (tests)

    def build_report(
        self,
        *,
        intent: Optional[TripIntent] = None,
        flight: Optional[FlightOption] = None,
        hotel: Optional[HotelOption] = None,
        budget: Optional[BudgetEstimate] = None,
        policy: Optional[PolicyResult] = None,
        approval: Optional[ApprovalResult] = None,
    ) -> str:
        """Return the executive report as a Markdown string."""
        facts = _facts(intent, flight, hotel, budget, policy, approval)
        if self._llm_enabled(get_settings()):
            try:
                markdown = self._call_model(build_executive_report_prompt(facts))
                if markdown and markdown.strip():
                    return markdown.strip()
            except Exception as exc:  # keep the deterministic report
                logger.warning("Gemini executive report failed; using fallback: %s", exc)
        return _deterministic_report(intent, flight, hotel, budget, policy, approval)

    def _llm_enabled(self, settings: Settings) -> bool:
        return self._use_llm if self._use_llm is not None else settings.llm_enabled

    def _call_model(self, prompt: str) -> str:
        if self._generate is not None:
            return self._generate(prompt)
        client = build_gemini_client()
        if client is None:
            raise RuntimeError("LLM is disabled; cannot call Gemini")
        # Use the advanced (Pro) model for the executive report.
        return client.generate(prompt, model=get_settings().gemini_advanced_model)

    def run(self, context: RunContext) -> str:
        return self.build_report(
            intent=context.get("intent"),
            flight=context.get("flight"),
            hotel=context.get("hotel"),
            budget=context.get("budget"),
            policy=context.get("policy"),
            approval=context.get("approval"),
        )


# --- facts + deterministic fallback ---------------------------------------- #
def _facts(intent, flight, hotel, budget, policy, approval) -> str:
    lines: list[str] = []
    if intent is not None:
        origin = intent.origin.label if intent.origin else "?"
        dest = intent.destination.label if intent.destination else "?"
        lines.append(f"Purpose: {intent.purpose or '-'}")
        if intent.event_name or intent.organization:
            lines.append(f"Event: {intent.event_name or '-'} / Organization: {intent.organization or '-'}")
        lines.append(f"Route: {origin} -> {dest}")
        lines.append(f"Dates: {intent.start_date} to {intent.end_date}")
    if flight is not None:
        lines.append(
            f"Flight: {flight.airline} {flight.flight_number} "
            f"{flight.origin_airport}->{flight.destination_airport} "
            f"depart {flight.departure_time} stops {flight.stops} "
            f"{flight.price:.2f} {flight.currency}"
        )
    if hotel is not None:
        lines.append(
            f"Hotel: {hotel.hotel_name} ({hotel.chain}) {hotel.nights} nights "
            f"total {hotel.total_price:.2f} {hotel.currency}"
        )
    if budget is not None:
        lines.append(
            f"Budget: flight {budget.flight_cost:.2f}, hotel {budget.hotel_cost:.2f}, "
            f"per_diem {budget.per_diem:.2f}, transport {budget.local_transport:.2f}, "
            f"contingency {budget.contingency:.2f}, TOTAL {budget.total:.2f} {budget.currency}"
        )
    if policy is not None:
        findings = "; ".join(f"{f.rule_id} {f.severity}: {f.message}" for f in policy.findings)
        lines.append(f"Policy: status={policy.status}; {findings}")
    if approval is not None:
        decision = approval.decision
        if decision is not None:
            lines.append(
                f"Approval: {approval.status.value} by {decision.reviewer} "
                f"at {decision.timestamp} ({decision.comments or '-'})"
            )
        else:
            lines.append(f"Approval: {approval.status.value}")
    return "\n".join(lines)


def _deterministic_report(intent, flight, hotel, budget, policy, approval) -> str:
    md: list[str] = ["# Executive Travel Recommendation", ""]

    md.append("## Purpose")
    if intent is not None and intent.purpose:
        md.append(intent.purpose)
        if intent.event_name or intent.organization:
            md.append(f"\nEvento: **{intent.event_name or '-'}** — Organização: **{intent.organization or '-'}**")
    else:
        md.append("Não informado.")
    md.append("")

    md.append("## Recommended Itinerary")
    if intent is not None:
        origin = intent.origin.label if intent.origin else "?"
        dest = intent.destination.label if intent.destination else "?"
        md.append(f"- **Rota:** {origin} → {dest}")
        md.append(f"- **Datas:** {intent.start_date} a {intent.end_date}")
    if flight is not None:
        md.append(
            f"- **Voo:** {flight.airline} {flight.flight_number} "
            f"({flight.origin_airport}→{flight.destination_airport}), "
            f"partida {flight.departure_time}, {flight.stops} parada(s), "
            f"{flight.price:.2f} {flight.currency}"
        )
    if hotel is not None:
        md.append(
            f"- **Hotel:** {hotel.hotel_name} ({hotel.chain}), "
            f"{hotel.nights} noites, {hotel.total_price:.2f} {hotel.currency}"
        )
    md.append("")

    md.append("## Cost Summary")
    if budget is not None:
        md.append(f"- Voo: {budget.flight_cost:.2f} {budget.currency}")
        md.append(f"- Hotel: {budget.hotel_cost:.2f} {budget.currency}")
        md.append(f"- Diárias (per diem): {budget.per_diem:.2f} {budget.currency}")
        md.append(f"- Transporte local: {budget.local_transport:.2f} {budget.currency}")
        md.append(f"- Contingência: {budget.contingency:.2f} {budget.currency}")
        md.append(f"- **Total: {budget.total:.2f} {budget.currency}**")
    else:
        md.append("Orçamento não disponível.")
    md.append("")

    md.append("## Policy Compliance")
    if policy is not None:
        md.append(f"**Status:** {policy.status.upper()}")
        for finding in policy.findings:
            md.append(f"- `{finding.rule_id}` **{finding.severity}** — {finding.message}")
    else:
        md.append("Validação de política não disponível.")
    md.append("")

    md.append("## Approval Status")
    if approval is not None:
        md.append(f"**Status:** {approval.status.value.upper()}")
        if approval.decision is not None:
            d = approval.decision
            md.append(f"- Revisor: **{d.reviewer}**")
            md.append(f"- Decisão: {d.decision} ({d.comments or 'sem comentários'})")
            md.append(f"- Data: {d.timestamp}")
    else:
        md.append("Aprovação pendente.")
    md.append("")

    md.append("## Final Recommendation")
    md.append(_final_recommendation(policy, approval, budget))
    return "\n".join(md).strip()


def _final_recommendation(policy, approval, budget) -> str:
    approved = approval is not None and approval.status.value == "approved"
    blocked = policy is not None and policy.status == "block"
    total = f"{budget.total:.2f} {budget.currency}" if budget is not None else "—"
    if blocked:
        return "**Não recomendado:** a viagem viola a política corporativa e não pode prosseguir."
    if approved:
        return (
            f"**Recomendado e aprovado.** Prosseguir com a reserva pelo custo "
            f"total estimado de {total}."
        )
    return (
        f"**Recomendado, pendente de aprovação.** Custo total estimado de {total}; "
        "aguardando decisão do gestor."
    )
