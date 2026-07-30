"""Tool Registry.

Tools are registered by name and invoked uniformly. The registry is what
`GET /tools` introspects to show the available tools and their schemas.
See specs/tools.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from pydantic import BaseModel


@dataclass
class ToolSpec:
    """Metadata + callable for a single registered tool."""

    name: str
    description: str
    input_model: Optional[type[BaseModel]] = None
    output_model: Optional[type[BaseModel]] = None
    simulated: bool = True
    handler: Optional[Callable[..., BaseModel]] = None


@dataclass
class ToolRegistry:
    """Holds the catalog of tools available to agents."""

    _tools: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def call(self, name: str, payload: BaseModel) -> BaseModel:
        """Invoke a tool by name with a typed payload."""
        spec = self._tools[name]
        if spec.handler is None:
            # TODO: wire each tool's handler so call() executes real logic.
            raise NotImplementedError(f"Tool '{name}' has no handler yet")
        return spec.handler(payload)


def build_default_registry() -> ToolRegistry:
    """Register the seven demo tools (metadata only at the skeleton stage)."""

    from app.schemas.budget import BudgetEstimate, BudgetInput
    from app.schemas.flight import FlightSearchInput, FlightSearchResult
    from app.schemas.hotel import HotelSearchInput, HotelSearchResult
    from app.schemas.memory import MemoryQuery, MemoryReadResult
    from app.schemas.policy import PolicyInput, PolicyResult
    from app.schemas.report import DocumentInput, TravelReport

    registry = ToolRegistry()
    # TODO: attach a `handler` to each ToolSpec once tool logic is implemented.
    registry.register(ToolSpec(
        name="google_flights_tool",
        description="Search flights via the (simulated) Google Flights / SerpAPI provider.",
        input_model=FlightSearchInput, output_model=FlightSearchResult,
    ))
    registry.register(ToolSpec(
        name="skyscanner_tool",
        description="Search flights via the (simulated) Skyscanner provider.",
        input_model=FlightSearchInput, output_model=FlightSearchResult,
    ))
    registry.register(ToolSpec(
        name="hotel_search_tool",
        description="Search hotels via the (simulated) hotel provider.",
        input_model=HotelSearchInput, output_model=HotelSearchResult,
    ))
    registry.register(ToolSpec(
        name="budget_calculator_tool",
        description="Compute total trip budget from flight + hotel + per-diem.",
        input_model=BudgetInput, output_model=BudgetEstimate,
    ))
    registry.register(ToolSpec(
        name="policy_tool",
        description="Evaluate corporate travel policy rules against the trip.",
        input_model=PolicyInput, output_model=PolicyResult,
    ))
    registry.register(ToolSpec(
        name="memory_tool",
        description="Read/write the SQLite-backed memory store.",
        input_model=MemoryQuery, output_model=MemoryReadResult,
    ))
    registry.register(ToolSpec(
        name="document_generator_tool",
        description="Generate the final travel justification/report.",
        input_model=DocumentInput, output_model=TravelReport,
    ))
    return registry
