"""HotelRankingAgent — ranks candidate hotels. Calls NO external tools.

Scores the HotelOptions from HotelSearchAgent using the applied hotel
preferences, in-process. Weighted signals (sum to 100, so the score is already
on a 0–100 scale):

  preferred chain match ......... 35  (highest weight)
  star rating (relative) ........ 25
  price (relative, cheaper=better) 25
  distance (relative, closer=better) 15

See specs/agents.md (HotelRankingAgent).
"""

from __future__ import annotations

from app.agents.base import Agent, RunContext
from app.core.ranking_config import HOTEL_RANKING_WEIGHTS
from app.schemas.hotel import HotelOption
from app.schemas.ranking import HotelRanking, RankedHotel

# Signal weights (sum = 100); sourced from app.core.ranking_config.
W_CHAIN = HOTEL_RANKING_WEIGHTS["preferred_chain"]
W_STARS = HOTEL_RANKING_WEIGHTS["stars"]
W_PRICE = HOTEL_RANKING_WEIGHTS["price"]
W_DISTANCE = HOTEL_RANKING_WEIGHTS["distance"]


class HotelRankingAgent(Agent):
    """Ranks hotels received from the search agent using preferences."""

    name = "HotelRankingAgent"

    def rank(
        self, options: list[HotelOption], preferences: dict[str, str]
    ) -> HotelRanking:
        if not options:
            return HotelRanking()

        stars = [o.stars for o in options]
        prices = [o.total_price for o in options]
        distances = [o.distance_km for o in options]
        min_stars, max_stars = min(stars), max(stars)
        min_price, max_price = min(prices), max(prices)
        min_dist, max_dist = min(distances), max(distances)

        preferred_chain = preferences.get("preferred_hotel_chain")

        scored: list[tuple[HotelOption, int, list[str]]] = []
        for option in options:
            score = 0.0
            reasons: list[str] = []

            # 1. Preferred chain match (highest weight).
            if preferred_chain and option.preferred_match:
                score += W_CHAIN
                reasons.append("preferred hotel chain")

            # 2. Star rating (higher is better).
            stars_component = self._higher_is_better(
                option.stars, min_stars, max_stars, W_STARS
            )
            score += stars_component
            if option.stars == max_stars:
                reasons.append("top rating")
            elif stars_component >= W_STARS / 2:
                reasons.append("good rating")

            # 3. Price (cheaper is better).
            price_component = self._lower_is_better(
                option.total_price, min_price, max_price, W_PRICE
            )
            score += price_component
            if option.total_price == min_price:
                reasons.append("lowest price")
            elif price_component >= W_PRICE / 2:
                reasons.append("competitive price")

            # 4. Distance (closer is better).
            dist_component = self._lower_is_better(
                option.distance_km, min_dist, max_dist, W_DISTANCE
            )
            score += dist_component
            if option.distance_km == min_dist:
                reasons.append("closest to destination")
            elif dist_component >= W_DISTANCE / 2:
                reasons.append("close to destination")

            scored.append((option, round(score), reasons))

        # Best-first; deterministic tie-break by price then id.
        scored.sort(key=lambda t: (-t[1], t[0].total_price, t[0].id))
        ranking = [
            RankedHotel(hotel_id=opt.id, score=sc, rank=i + 1, reasons=rs)
            for i, (opt, sc, rs) in enumerate(scored)
        ]
        return HotelRanking(recommended_hotel=scored[0][0], hotel_ranking=ranking)

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _lower_is_better(value: float, low: float, high: float, weight: int) -> float:
        """Linear score in [0, weight]; cheapest/closest = full, dearest/farthest = 0."""
        if high == low:
            return float(weight)
        return weight * (high - value) / (high - low)

    @staticmethod
    def _higher_is_better(value: float, low: float, high: float, weight: int) -> float:
        """Linear score in [0, weight]; highest = full, lowest = 0."""
        if high == low:
            return float(weight)
        return weight * (value - low) / (high - low)

    def run(self, context: RunContext) -> HotelRanking:
        return self.rank(context["hotel_options"], context.get("preferences", {}))
