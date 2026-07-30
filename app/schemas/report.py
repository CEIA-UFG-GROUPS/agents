"""Travel report schemas. See specs/tools.md (document_generator_tool).

The report is assembled deterministically from existing TripRun data — no LLM.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.budget import BudgetEstimate
from app.schemas.policy import PolicyResult


class DocumentInput(BaseModel):
    """Everything the DocumentAgent needs to assemble the report."""

    intent: Optional[Any] = None
    flight: Optional[Any] = None
    hotel: Optional[Any] = None
    budget: Optional[Any] = None
    policy: Optional[Any] = None
    approval: Optional[Any] = None


class ReportItinerary(BaseModel):
    origin: Optional[str] = None
    destination: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class ReportFlight(BaseModel):
    airline: str
    flight_number: str
    departure_time: str
    arrival_time: str
    price: float
    currency: str = "BRL"


class ReportHotel(BaseModel):
    hotel_name: str
    chain: str
    nights: int
    total_price: float
    currency: str = "BRL"


class TravelReport(BaseModel):
    """Final travel justification/report (produced post-approval)."""

    title: str = "Relatório de Viagem Corporativa"
    purpose: Optional[str] = None
    itinerary: ReportItinerary = Field(default_factory=ReportItinerary)
    selected_flight: Optional[ReportFlight] = None
    selected_hotel: Optional[ReportHotel] = None
    budget_summary: Optional[BudgetEstimate] = None
    policy_summary: Optional[PolicyResult] = None
    justification: list[str] = Field(default_factory=list)
    generated_at: Optional[datetime] = None
