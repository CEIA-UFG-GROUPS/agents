"""Schemas for provider-based airport/location resolution.

The TravelPlannerAgent extracts only textual locations; the LocationResolverTool
(and its providers) turn a city/region/country into an airport IATA code.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LocationQuery(BaseModel):
    """A place to resolve into an airport.

    `location_text` is the raw mention; `request_text` / `intent_summary` give
    the LLM the surrounding context (ignored by the offline provider).
    """

    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    free_text: Optional[str] = None
    location_text: Optional[str] = None
    request_text: Optional[str] = None
    intent_summary: Optional[str] = None


class AirportOption(BaseModel):
    """A candidate airport (used when a place is ambiguous)."""

    airport: str
    airport_name: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None


class ResolvedLocation(BaseModel):
    """Result of resolving a LocationQuery."""

    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    airport: Optional[str] = None
    airport_name: Optional[str] = None
    confidence: float = 0.0
    is_ambiguous: bool = False
    reason: Optional[str] = None
    requires_clarification: bool = False
    options: list[AirportOption] = Field(default_factory=list)
