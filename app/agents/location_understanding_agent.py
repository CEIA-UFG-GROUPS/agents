"""LocationUnderstandingAgent — resolves origin/destination airports.

Given the user request and the current TripIntent, it resolves any missing
airports via the LocationResolverTool (Gemini when LLM_ENABLED=true, else the
offline demo provider) and decides whether clarification is required. It does
NOT hardcode airport mappings — that lives in the tool/providers.
See specs/agents.md.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.agents.base import Agent, RunContext
from app.agents.clarification_agent import ClarificationAgent
from app.schemas.location import AirportOption, LocationQuery
from app.schemas.trip import TripIntent
from app.tools.location_resolver_tool import LocationResolverTool


class LocationUnderstanding(BaseModel):
    """Result of the LocationUnderstandingAgent."""

    intent: TripIntent
    requires_clarification: bool = False
    clarification_question: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


class LocationUnderstandingAgent(Agent):
    """Resolves airports and validates the fields needed for flight search."""

    name = "LocationUnderstandingAgent"

    def __init__(
        self,
        resolver: Optional[LocationResolverTool] = None,
        clarification_agent: Optional[ClarificationAgent] = None,
    ) -> None:
        self.resolver = resolver or LocationResolverTool()
        self.clarification_agent = clarification_agent or ClarificationAgent()

    def understand(self, request_text: str, intent: TripIntent) -> LocationUnderstanding:
        ambiguous: dict[str, list[AirportOption]] = {}
        notes: list[str] = []
        summary = _intent_summary(intent)

        for side in ("origin", "destination"):
            loc = getattr(intent, side)
            if loc is None or loc.airport is not None:
                continue
            if not (loc.city or loc.region or loc.country):
                continue
            resolved = self.resolver.resolve(
                LocationQuery(
                    city=loc.city, region=loc.region, country=loc.country,
                    location_text=loc.city, request_text=request_text,
                    intent_summary=summary,
                )
            )
            if resolved.requires_clarification:
                if resolved.options:
                    ambiguous[side] = resolved.options
                    notes.append(f"{side}: ambiguous")
                continue
            loc.airport = resolved.airport
            loc.region = loc.region or resolved.region
            loc.country = loc.country or resolved.country

        # Degenerate trip: origin airport equals destination airport.
        if (
            intent.origin and intent.destination
            and intent.origin.airport
            and intent.origin.airport == intent.destination.airport
        ):
            intent.origin.airport = None

        # Inverted dates (ida depois da volta) → descarta e pede de novo,
        # evitando um erro mais adiante no orçamento.
        if (
            intent.start_date and intent.end_date
            and intent.end_date < intent.start_date
        ):
            intent.start_date = None
            intent.end_date = None

        # Deterministic decision (what's missing / ambiguous) stays here; the
        # ClarificationAgent only phrases the question.
        missing = _missing_required_fields(intent)
        ambiguity = None
        if "destination" in ambiguous:
            ambiguity = ("destination", ambiguous["destination"])
        elif "origin" in ambiguous:
            ambiguity = ("origin", ambiguous["origin"])

        result = self.clarification_agent.clarify(missing, ambiguity)
        return LocationUnderstanding(
            intent=intent,
            requires_clarification=result.requires_clarification,
            clarification_question=result.question,
            notes=notes,
        )

    def run(self, context: RunContext) -> LocationUnderstanding:
        return self.understand(context.get("request_text", ""), context["intent"])


# --- helpers --------------------------------------------------------------- #
def _missing_required_fields(intent: Optional[TripIntent]) -> list[str]:
    missing: list[str] = []
    if not (intent and intent.origin and intent.origin.airport):
        missing.append("origin_airport")
    if not (intent and intent.destination and intent.destination.airport):
        missing.append("destination_airport")
    if not (intent and intent.start_date):
        missing.append("start_date")
    if not (intent and intent.end_date):
        missing.append("end_date")
    return missing


def _intent_summary(intent: Optional[TripIntent]) -> str:
    if intent is None:
        return ""
    origin = intent.origin.city if intent.origin else None
    dest = intent.destination.city if intent.destination else None
    return f"origin={origin}; destination={dest}; {intent.start_date}..{intent.end_date}"
