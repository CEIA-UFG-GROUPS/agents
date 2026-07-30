"""Budget assumptions for the BudgetAgent.

Kept in one place so the budget policy is explicit and tunable without editing
agent logic. See specs/agents.md (BudgetAgent).
"""

from __future__ import annotations

PER_DIEM_RATE = 120  # BRL per day
LOCAL_TRANSPORT = 300  # BRL fixed
CONTINGENCY_RATE = 0.10  # fraction of the subtotal before contingency
DEFAULT_CURRENCY = "BRL"
