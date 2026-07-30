"""PolicyAgent — validates the trip against corporate travel policy.

Delegates rule evaluation to policy_tool. A `block` status must prevent the run
from advancing to approval (enforced by the orchestrator). See specs/agents.md.
"""

from __future__ import annotations

from typing import Optional

from app.agents.base import Agent, RunContext
from app.schemas.budget import BudgetEstimate
from app.schemas.flight import FlightOption
from app.schemas.hotel import HotelOption
from app.schemas.policy import PolicyInput, PolicyResult
from app.schemas.trip import TripIntent
from app.tools.policy_tool import PolicyTool


class PolicyAgent(Agent):
    """Runs the policy_tool over the recommended trip + budget."""

    name = "PolicyAgent"

    def __init__(self, policy_tool: Optional[PolicyTool] = None) -> None:
        self.policy_tool = policy_tool or PolicyTool()

    def validate(
        self,
        intent: Optional[TripIntent],
        recommended_flight: Optional[FlightOption],
        recommended_hotel: Optional[HotelOption],
        budget_estimate: Optional[BudgetEstimate],
    ) -> PolicyResult:
        payload = PolicyInput(
            intent=intent,
            flight=recommended_flight,
            hotel=recommended_hotel,
            budget=budget_estimate,
        )
        return self.policy_tool.evaluate(payload)

    def run(self, context: RunContext) -> PolicyResult:
        return self.validate(
            context.get("intent"),
            context.get("recommended_flight"),
            context.get("recommended_hotel"),
            context.get("budget_estimate"),
        )
