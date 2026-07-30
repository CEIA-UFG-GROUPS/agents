"""budget_calculator_tool — transparent trip-budget formula. See specs/tools.md."""

from __future__ import annotations

from app.schemas.budget import BudgetEstimate, BudgetInput


class BudgetCalculatorTool:
    """Compute total = flights + hotel + per_diem_rate * days."""

    name = "budget_calculator_tool"

    def calculate(self, payload: BudgetInput) -> BudgetEstimate:
        # TODO: implement the formula and populate the breakdown lines.
        return BudgetEstimate(currency=payload.currency)
