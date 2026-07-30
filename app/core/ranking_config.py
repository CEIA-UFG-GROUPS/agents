"""Ranking weights for the Flight/Hotel ranking agents.

Kept in one place so the scoring policy is explicit and tunable without editing
agent logic. Each weight map sums to 100, so an agent's raw score is already on
a 0–100 scale. See specs/agents.md (FlightRankingAgent, HotelRankingAgent).
"""

from __future__ import annotations

FLIGHT_RANKING_WEIGHTS: dict[str, int] = {
    "non_stop": 30,
    "morning_departure": 20,
    "price": 25,
    "duration": 15,
    "preferred_seat": 10,
}

HOTEL_RANKING_WEIGHTS: dict[str, int] = {
    "preferred_chain": 35,
    "stars": 25,
    "price": 25,
    "distance": 15,
}
