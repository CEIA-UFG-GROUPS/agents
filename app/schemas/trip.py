"""Trip-level schemas: the request, intent, plan, run, and ranking results.

See specs/architecture.md (Run State Machine + Data Model).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, computed_field, model_validator

from app.schemas.approval import ApprovalResult
from app.schemas.budget import BudgetEstimate
from app.schemas.flight import FlightOption
from app.schemas.hotel import HotelOption
from app.schemas.policy import PolicyResult
from app.schemas.ranking import FlightRanking, RankedHotel
from app.schemas.recommendation import RecommendedTrip
from app.schemas.report import TravelReport


class TripPhase(str, Enum):
    """Ordered phases a TripRun moves through (see state_machine.py)."""

    CREATED = "CREATED"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    RETRIEVING_MEMORY = "RETRIEVING_MEMORY"
    RESOLVING_LOCATIONS = "RESOLVING_LOCATIONS"
    SEARCHING_FLIGHTS = "SEARCHING_FLIGHTS"
    SEARCHING_HOTELS = "SEARCHING_HOTELS"
    RANKING_FLIGHTS = "RANKING_FLIGHTS"
    RANKING_HOTELS = "RANKING_HOTELS"
    RECOMMENDING = "RECOMMENDING"
    ESTIMATING_BUDGET = "ESTIMATING_BUDGET"
    VALIDATING_POLICY = "VALIDATING_POLICY"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    GENERATING_REPORT = "GENERATING_REPORT"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class TripRequest(BaseModel):
    """Inbound natural-language travel request (POST /trips)."""

    request_text: str = Field(
        ...,
        examples=[
            "Preciso planejar uma viagem corporativa para Goiânia entre 08 e 13 "
            "de junho para conduzir workshops e reuniões do EnergyGPT."
        ],
    )


class Location(BaseModel):
    """A reusable place: city + airport (+ optional region/country)."""

    city: Optional[str] = None
    airport: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None

    @property
    def label(self) -> Optional[str]:
        """Human-readable "City (CODE)" when both are present."""
        if self.city and self.airport:
            return f"{self.city} ({self.airport})"
        return self.city or self.airport


class ClarifyRequest(BaseModel):
    """Inbound clarification reply for an existing trip (POST /trips/{id}/clarify)."""

    message: str = Field(
        ...,
        examples=["ida em 29-06-2026, volta em 10-07-2026"],
    )


class TripIntent(BaseModel):
    """Structured intent parsed from the request by the TravelPlannerAgent.

    Origin and destination are nested `Location` objects (the canonical, internal
    representation). For backward compatibility the model ALSO accepts the flat
    `origin_city` / `origin_airport` / `destination_city` / `destination_airport`
    fields on input and exposes them as read-only properties — but internal code
    should prefer `intent.origin.city`, `intent.destination.airport`, etc.
    """

    origin: Optional[Location] = None
    destination: Optional[Location] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    purpose: Optional[str] = None
    traveler: Optional[str] = None
    event_name: Optional[str] = None
    organization: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _accept_flat_fields(cls, data: Any) -> Any:
        """Build nested Locations from flat *_city/*_airport input (back-compat)."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if not data.get("origin"):
            city, airport = data.pop("origin_city", None), data.pop("origin_airport", None)
            if city or airport:
                data["origin"] = {"city": city, "airport": airport}
        else:
            data.pop("origin_city", None)
            data.pop("origin_airport", None)
        if not data.get("destination"):
            city = data.pop("destination_city", None)
            airport = data.pop("destination_airport", None)
            if city or airport:
                data["destination"] = {"city": city, "airport": airport}
        else:
            data.pop("destination_city", None)
            data.pop("destination_airport", None)
        return data

    # --- backward-compatible read accessors (not serialized) -------------
    @property
    def origin_city(self) -> Optional[str]:
        return self.origin.city if self.origin else None

    @property
    def origin_airport(self) -> Optional[str]:
        return self.origin.airport if self.origin else None

    @property
    def destination_city(self) -> Optional[str]:
        return self.destination.city if self.destination else None

    @property
    def destination_airport(self) -> Optional[str]:
        return self.destination.airport if self.destination else None

    # --- combined-string views (kept for display / older consumers) ------
    @computed_field  # type: ignore[prop-decorator]
    @property
    def origin_label(self) -> Optional[str]:
        return self.origin.label if self.origin else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def destination_label(self) -> Optional[str]:
        return self.destination.label if self.destination else None


class PlanItem(BaseModel):
    """A single, ordered step in the travel plan."""

    step: str
    description: str
    agent: str


class TravelPlan(BaseModel):
    """Explicit ordered plan emitted by the TravelPlannerAgent."""

    items: list[PlanItem] = Field(default_factory=list)


class Step(BaseModel):
    """A recorded execution step (agent/tool call) for inspection."""

    name: str
    status: str = "done"
    order: int
    input: Optional[Any] = None
    output: Optional[Any] = None


class TripRun(BaseModel):
    """The central resource: a trip-planning run and its accumulated state."""

    id: str
    request_text: str
    phase: TripPhase = TripPhase.CREATED
    created_at: datetime

    intent: Optional[TripIntent] = None
    plan: Optional[TravelPlan] = None
    flight_options: list[FlightOption] = Field(default_factory=list)
    hotel_options: list[HotelOption] = Field(default_factory=list)
    flight_ranking: Optional[FlightRanking] = None
    recommended_hotel: Optional[HotelOption] = None
    hotel_ranking: list[RankedHotel] = Field(default_factory=list)
    recommended_trip: Optional[RecommendedTrip] = None
    budget_estimate: Optional[BudgetEstimate] = None
    policy_result: Optional[PolicyResult] = None
    approval_result: Optional[ApprovalResult] = None
    report: Optional[TravelReport] = None
    steps: list[Step] = Field(default_factory=list)

    # Set by the MemoryAgent when it cannot safely infer a missing origin
    # (e.g. the only known origin equals the destination). No clarification
    # endpoint exists yet — these just surface the open question.
    requires_clarification: bool = False
    clarification_question: Optional[str] = None
    # Heavier sub-objects (flights, hotels, budget, policy, report) are attached
    # by the orchestrator as the run advances.
    # TODO: reference flight/hotel/budget/policy/report schemas once the
    #       orchestrator populates them.
