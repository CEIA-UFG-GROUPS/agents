"""FlightRankingAgent — ranks candidate flights. Calls NO external tools.

Scores the FlightOptions from FlightSearchAgent using traveler preferences from
memory, in-process. Weighted signals (sum to 100, so the score is already on a
0–100 scale):

  non-stop flight ............... 30
  preferred departure time ...... 20
  lowest price (relative) ....... 25
  shortest duration (relative) .. 15
  preferred seat type available . 10

See specs/agents.md (FlightRankingAgent).
"""

from __future__ import annotations

from app.agents.base import Agent, RunContext
from app.core.ranking_config import FLIGHT_RANKING_WEIGHTS
from app.schemas.flight import FlightOption
from app.schemas.ranking import FlightRanking, RankedFlight

# Signal weights (sum = 100); sourced from app.core.ranking_config.
W_NONSTOP = FLIGHT_RANKING_WEIGHTS["non_stop"]
W_DEPARTURE = FLIGHT_RANKING_WEIGHTS["morning_departure"]
W_PRICE = FLIGHT_RANKING_WEIGHTS["price"]
W_DURATION = FLIGHT_RANKING_WEIGHTS["duration"]
W_SEAT = FLIGHT_RANKING_WEIGHTS["preferred_seat"]

# Departure-time buckets by hour-of-day.
_TIME_BUCKETS = {
    "morning": range(6, 12),
    "afternoon": range(12, 18),
    "evening": list(range(18, 24)) + list(range(0, 6)),
}


class FlightRankingAgent(Agent):
    """Ranks flights received from the search agent using preferences."""

    name = "FlightRankingAgent"

    def rank(
        self, options: list[FlightOption], preferences: dict[str, str]
    ) -> FlightRanking:
        if not options:
            return FlightRanking()

        prices = [o.price for o in options]
        durations = [o.duration_minutes for o in options]
        min_price, max_price = min(prices), max(prices)
        min_dur, max_dur = min(durations), max(durations)

        pref_departure = preferences.get("preferred_departure_time")
        pref_seat = preferences.get("preferred_seat_type")

        scored: list[tuple[FlightOption, int, list[str]]] = []
        for option in options:
            score = 0.0
            reasons: list[str] = []

            # 1. Stops — fewer is better. Non-stop gets the full weight; with
            #    stops the weight decays (W/(1+stops)), so when every option has
            #    stops (international routes) the signal no longer dominates and
            #    fewer stops are still preferred.
            score += W_NONSTOP / (1 + option.stops)
            if option.stops == 0:
                reasons.append("non-stop")
            elif option.stops == 1:
                reasons.append("1 stop")
            else:
                reasons.append(f"{option.stops} stops")

            # 2. Preferred departure time.
            if pref_departure and self._in_bucket(option, pref_departure):
                score += W_DEPARTURE
                reasons.append(f"{pref_departure} departure")

            # 3. Lowest price (linear: cheapest = full weight, dearest = 0).
            price_component = self._relative(option.price, min_price, max_price, W_PRICE)
            score += price_component
            if option.price == min_price:
                reasons.append("lowest price")
            elif price_component >= W_PRICE / 2:
                reasons.append("competitive price")

            # 4. Shortest duration (linear).
            dur_component = self._relative(
                option.duration_minutes, min_dur, max_dur, W_DURATION
            )
            score += dur_component
            if option.duration_minutes == min_dur:
                reasons.append("shortest duration")
            elif dur_component >= W_DURATION / 2:
                reasons.append("short duration")

            # 5. Preferred seat type available — only when the traveler has a
            #    preference AND this flight actually offers that seat.
            if pref_seat and option.preferred_seat_available:
                score += W_SEAT
                reasons.append(f"preferred {pref_seat} seat available")

            scored.append((option, round(score), reasons))

        # Best-first; deterministic tie-break by price then id.
        scored.sort(key=lambda t: (-t[1], t[0].price, t[0].id))

        # Defensive: guarantee unique flight ids in the ranking. Order is
        # preserved and the highest-ranked (first) occurrence is kept, so scores
        # and ordering are unaffected when the input is already unique.
        seen: set[str] = set()
        unique: list[tuple[FlightOption, int, list[str]]] = []
        for option, sc, rs in scored:
            if option.id in seen:
                continue
            seen.add(option.id)
            unique.append((option, sc, rs))

        ranking = [
            RankedFlight(flight_id=opt.id, score=sc, rank=i + 1, reasons=rs)
            for i, (opt, sc, rs) in enumerate(unique)
        ]
        return FlightRanking(recommended_flight=unique[0][0], ranking=ranking)

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _relative(value: float, low: float, high: float, weight: int) -> float:
        """Lower-is-better linear score in [0, weight]; full weight if no range."""
        if high == low:
            return float(weight)
        return weight * (high - value) / (high - low)

    @staticmethod
    def _in_bucket(option: FlightOption, bucket: str) -> bool:
        """Does the option's departure hour fall in the named time bucket?"""
        hours = _TIME_BUCKETS.get(bucket.lower())
        if hours is None:
            return False
        # departure_time looks like "2026-06-08T06:10:00".
        try:
            hour = int(option.departure_time[11:13])
        except (ValueError, IndexError):
            return False
        return hour in hours

    def run(self, context: RunContext) -> FlightRanking:
        return self.rank(context["flight_options"], context.get("preferences", {}))
