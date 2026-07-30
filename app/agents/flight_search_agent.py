"""FlightSearchAgent — finds candidate flights via the flight tools.

Calls both google_flights_tool and skyscanner_tool, then merges their options
into a single list of 5: the first 3 from google_flights and the next 2 from
skyscanner. Each option keeps its own `provider`. See specs/agents.md.
"""

from __future__ import annotations

from app.agents.base import Agent, RunContext
from app.schemas.flight import FlightOption, FlightSearchInput
from app.schemas.trip import TripIntent
from app.tools.google_flights_tool import GoogleFlightsTool
from app.tools.skyscanner_tool import SkyscannerTool

# How many options to take from each source when merging.
GOOGLE_COUNT = 3
SKYSCANNER_COUNT = 2


class FlightSearchAgent(Agent):
    """Queries google_flights_tool and skyscanner_tool, merges the results."""

    name = "FlightSearchAgent"

    def __init__(self, google_flights_tool=None, skyscanner_tool=None) -> None:
        self.google_flights_tool = google_flights_tool or GoogleFlightsTool()
        self.skyscanner_tool = skyscanner_tool or SkyscannerTool()

    def search(self, intent: TripIntent) -> list[FlightOption]:
        """Build the query from the (enriched) intent and call both tools."""
        options, _ = self.search_with_trace(intent)
        return options

    def search_with_trace(
        self, intent: TripIntent
    ) -> tuple[list[FlightOption], list[dict]]:
        """Same search, also returning a per-tool call log for observability."""
        query = FlightSearchInput(
            origin=intent.origin.airport if intent.origin else None,
            destination=intent.destination.airport if intent.destination else None,
            depart_date=intent.start_date,
            passengers=1,
            origin_country=intent.origin.country if intent.origin else None,
            destination_country=intent.destination.country if intent.destination else None,
        )
        tool_calls: list[dict] = []
        google = self.google_flights_tool.search(query).options
        tool_calls.append({"tool": self.google_flights_tool.name, "status": "success"})
        skyscanner = self.skyscanner_tool.search(query).options
        tool_calls.append({"tool": self.skyscanner_tool.name, "status": "success"})
        # 3 from google + the next 2 distinct flights from skyscanner = 5 total,
        # each preserving its source provider.
        options = (
            google[:GOOGLE_COUNT]
            + skyscanner[GOOGLE_COUNT:GOOGLE_COUNT + SKYSCANNER_COUNT]
        )
        return options, tool_calls

    def run(self, context: RunContext) -> list[FlightOption]:
        return self.search(context["intent"])
