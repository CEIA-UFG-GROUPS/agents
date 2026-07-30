"""Corporate travel policy thresholds for the PolicyAgent / policy_tool.

Kept in one place so the policy is explicit and tunable without editing logic.
See specs/tools.md (policy_tool) and specs/agents.md (PolicyAgent).
"""

from __future__ import annotations

# R2 — total budget bands (BRL).
TRIP_BUDGET_LIMIT = 8000  # <= limit => pass
TRIP_BUDGET_BLOCK = 10000  # > limit and <= block => warn; > block => block

# R3 — hotel nightly rate ceiling (BRL/night). Above => warn.
HOTEL_NIGHTLY_LIMIT = 500
