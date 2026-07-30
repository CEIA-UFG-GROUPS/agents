"""Budget estimation schemas. See specs/tools.md (budget_calculator_tool)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BudgetInput(BaseModel):
    """Inputs to the transparent budget formula."""

    flight_price: float = 0.0
    hotel_total: float = 0.0
    nights: int = 1
    per_diem_rate: float = 0.0
    currency: str = "BRL"


class BudgetEstimate(BaseModel):
    """Total trip budget with a transparent, human-readable breakdown."""

    flight_cost: float = 0.0
    hotel_cost: float = 0.0
    per_diem: float = 0.0
    local_transport: float = 0.0
    contingency: float = 0.0
    total: float = 0.0
    currency: str = "BRL"
    # Date-derived counts (from the trip's start/end dates), stored explicitly.
    inclusive_days: int = 0
    hotel_nights: int = 0
    breakdown: list[str] = Field(default_factory=list)
