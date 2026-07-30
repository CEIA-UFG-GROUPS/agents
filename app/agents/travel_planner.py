"""TravelPlannerAgent — understands the request and emits an explicit plan.

`understand()` delegates to the IntentUnderstandingAgent (Gemini when
LLM_ENABLED=true, else the deterministic parser below). `plan()` returns the
explicit, ordered TravelPlan. See specs/agents.md.
"""

from __future__ import annotations

import re
from datetime import date

from app.agents.base import Agent, RunContext
from app.schemas.trip import Location, PlanItem, TravelPlan, TripIntent

# The explicit, ordered plan the planner produces (spec'd in agents.md).
PLAN_STEPS: list[PlanItem] = [
    PlanItem(step="retrieve_memory", description="Load traveler preferences and prior trips", agent="MemoryAgent"),
    PlanItem(step="search_flights", description="Find candidate flights", agent="FlightSearchAgent"),
    PlanItem(step="search_hotels", description="Find candidate hotels", agent="HotelSearchAgent"),
    PlanItem(step="rank_flights", description="Score and rank flights", agent="FlightRankingAgent"),
    PlanItem(step="rank_hotels", description="Score and rank hotels", agent="HotelRankingAgent"),
    PlanItem(step="recommend_travel", description="Pick the best flight + hotel pair", agent="TravelRecommendationAgent"),
    PlanItem(step="estimate_budget", description="Total flights + hotel + per-diem", agent="BudgetAgent"),
    PlanItem(step="validate_policy", description="Check corporate travel policy", agent="PolicyAgent"),
    PlanItem(step="wait_for_approval", description="Pause for human approval", agent="HumanApproval"),
    PlanItem(step="generate_report", description="Produce the travel justification", agent="DocumentAgent"),
]

# Portuguese months in calendar order (canonical, accented names).
_MONTHS_ORDERED: list[tuple[str, int]] = [
    ("janeiro", 1), ("fevereiro", 2), ("março", 3), ("abril", 4),
    ("maio", 5), ("junho", 6), ("julho", 7), ("agosto", 8),
    ("setembro", 9), ("outubro", 10), ("novembro", 11), ("dezembro", 12),
]
_MONTHS_PT: dict[str, int] = {name: num for name, num in _MONTHS_ORDERED}
_MONTHS_PT["marco"] = 3  # accent-free variant

# NOTE: airport codes are intentionally NOT decided here. The planner extracts
# textual locations (city + optional region); the LocationResolverTool resolves
# the airport. See app/tools/location_resolver_tool.py.

# A capitalized city phrase, plus an optional ", Region" / " - Region" suffix
# (the region capture stops before a comma, period, "entre" or a "de <day>").
_CITY = r"([A-ZÀ-Ý][\wÀ-ÿ'’-]*(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'’-]*)*)"
_REGION = (
    r"(?:\s*[,\-–]\s*([A-Za-zÀ-ÿ][\wÀ-ÿ'’ \-]*?)"
    r"(?=\s*(?:,|\.|\bentre\b|\bde\s+\d|$)))?"
)
# Optional IATA code the user spelled out, e.g. "São Paulo (GRU)".
_AIRPORT_SUFFIX = r"(?:\s*\(\s*([A-Z]{3})\s*\))?"
_PARENTHESIZED_CODE = re.compile(r"\(\s*([A-Z]{3})\s*\)")


def _location_from(
    city_phrase: str | None,
    region_phrase: str | None,
    airport_code: str | None = None,
) -> Location:
    """Build a Location from captured text.

    An explicit 3-letter uppercase token is treated as an airport the user gave;
    otherwise only city/region are set and the airport stays None (unless the
    user spelled the code out, e.g. "São Paulo (GRU)").
    """
    city = city_phrase.strip(" ,.;-") if city_phrase else None
    if city and re.fullmatch(r"[A-Z]{3}", city):
        return Location(airport=city)
    region = region_phrase.strip(" ,.;-") if region_phrase else None
    return Location(city=city or None, region=region or None, airport=airport_code or None)


def _search_location(cue_pattern: str, text: str) -> Location | None:
    """Find a place after a cue (e.g. 'para', 'de') and return its Location."""
    m = re.search(cue_pattern + r"\s+" + _CITY + _REGION + _AIRPORT_SUFFIX, text)
    return _location_from(m.group(1), m.group(2), m.group(3)) if m else None


def location_from_answer(text: str | None) -> Location | None:
    """Location from a clarification answer, preserving an explicit IATA code.

    Unlike `location_from_mention`, this keeps the code the user (or the LLM)
    spelled out — "São Paulo (GRU)" and a bare "GRU" both yield airport=GRU.
    """
    if not text or not text.strip():
        return None
    match = _PARENTHESIZED_CODE.search(text)
    if not match:
        return location_from_mention(text)
    location = location_from_mention(_PARENTHESIZED_CODE.sub("", text)) or Location()
    location.airport = match.group(1)
    return location


def _resolve_month(token: str) -> int | None:
    """Resolve a month name/abbreviation/prefix to its number (1-12)."""
    t = token.lower().strip(".")
    if not t:
        return None
    if t in _MONTHS_PT:
        return _MONTHS_PT[t]
    for name, num in _MONTHS_ORDERED:  # prefix match, calendar order (ju -> junho)
        if name.startswith(t):
            return num
    return None


def _normalize_year(captured: str | None, default_year: int) -> int:
    """Two-digit -> 20xx; four-digit as-is; missing -> default."""
    if not captured:
        return default_year
    year = int(captured)
    return 2000 + year if year < 100 else year


def _make_date(year: int, month: int | None, day: int) -> date | None:
    try:
        return date(year, month, day) if month else None
    except (ValueError, TypeError):
        return None


def parse_intent_deterministic(request_text: str, default_year: int) -> TripIntent:
    """Deterministic, offline parser (the fallback when the LLM is off/fails).

    Only extracts what the request explicitly states; origin stays null when not
    mentioned and airport codes are never decided here.
    """
    text = request_text.strip()
    event_name, organization = _parse_event(text)
    return TripIntent(
        origin=TravelPlannerAgent._parse_origin(text),
        destination=TravelPlannerAgent._parse_destination(text),
        **dict(zip(("start_date", "end_date"), TravelPlannerAgent._parse_dates(text, default_year))),
        purpose=TravelPlannerAgent._parse_purpose(text),
        event_name=event_name,
        organization=organization,
        traveler=None,
    )


def _parse_event(text: str) -> tuple[str | None, str | None]:
    """Extract "evento <EventName> da/de <Organization>" when present."""
    match = re.search(
        r"\bevento\s+"
        r"([A-ZÀ-Ý][\wÀ-ÿ.&/-]*(?:\s+[A-ZÀ-Ý][\wÀ-ÿ.&/-]*)*)"
        r"\s+(?:da|de|do|na|no)\s+"
        r"([A-ZÀ-Ý][\wÀ-ÿ.&/-]+)",
        text,
    )
    if not match:
        return None, None
    return match.group(1).strip(" .,;"), match.group(2).strip(" .,;")


def location_from_mention(text: str | None) -> Location | None:
    """Build a Location from a free-text mention like "San Jose, California".

    Splits city / region on the first comma or hyphen; airport stays null
    (resolution is the LocationResolverTool's job).
    """
    if not text or not text.strip():
        return None
    parts = re.split(r"[,\-–]", text, maxsplit=1)
    city = parts[0].strip()
    region = parts[1].strip() if len(parts) > 1 else None
    return _location_from(city, region)


class TravelPlannerAgent(Agent):
    """Parses the request into a TripIntent and builds the ordered plan."""

    name = "TravelPlannerAgent"

    def __init__(self, intent_agent=None) -> None:
        self._intent_agent = intent_agent

    def understand(self, request_text: str) -> TripIntent:
        """Extract the TripIntent (via IntentUnderstandingAgent → LLM/fallback)."""
        return self._agent().understand(request_text)

    def _agent(self):
        if self._intent_agent is None:
            # Lazy import avoids a circular import (the intent agent imports the
            # deterministic parser from this module).
            from app.agents.intent_understanding_agent import IntentUnderstandingAgent
            self._intent_agent = IntentUnderstandingAgent()
        return self._intent_agent

    def plan(self, intent: TripIntent | None = None) -> TravelPlan:
        """Return the explicit, ordered travel plan (same steps for the demo)."""
        # The plan shape is fixed for the demo; `intent` is accepted so real
        # tailoring can be added later without changing callers.
        return TravelPlan(items=list(PLAN_STEPS))

    def run(self, context: RunContext) -> TravelPlan:
        intent = self.understand(context.get("request_text", ""))
        return self.plan(intent)

    # --- parsing helpers -------------------------------------------------

    @staticmethod
    def _parse_origin(text: str) -> Location | None:
        """Origin is parsed ONLY when explicitly stated, e.g. "de/desde <City>".

        Returns None when no origin is mentioned, so the MemoryAgent can fill it
        in later — the planner never invents an origin. Airport stays null.
        """
        return _search_location(r"\b(?:de|desde|partindo de|saindo de)\b", text)

    @staticmethod
    def _parse_destination(text: str) -> Location | None:
        """Destination = the place following 'para'. Airport stays null."""
        return _search_location(r"\bpara\b", text)

    @staticmethod
    def _parse_dates(text: str, default_year: int) -> tuple[date | None, date | None]:
        """Parse a Portuguese date range into (start, end).

        Supports:
          - numeric:        "entre 29/06 e 10/07", "entre 29-06 e 10-07"
          - month names:    "entre 29 de junho de 2026 e 10 de julho de 2026",
                            "entre 29 de ju e 10 de julho"
          - same month:     "entre 08 e 13 de junho"
        Year defaults to `default_year` when not stated.
        """
        # Numeric DD/MM (or DD-MM) for both endpoints, optional trailing year.
        m = re.search(
            r"entre\s+(\d{1,2})[/-](\d{1,2})\s+e\s+(\d{1,2})[/-](\d{1,2})"
            r"(?:[/-](\d{2,4}))?",
            text, re.IGNORECASE,
        )
        if m:
            d1, mo1, d2, mo2, yr = m.groups()
            year = _normalize_year(yr, default_year)
            return _make_date(year, int(mo1), int(d1)), _make_date(year, int(mo2), int(d2))

        # Two dates, each "DD de <month> [de YYYY]" (months may differ).
        m = re.search(
            r"entre\s+(\d{1,2})\s+de\s+([A-Za-zçÇà-ÿÀ-Ý.]+)(?:\s+de\s+(\d{4}))?"
            r"\s+e\s+(\d{1,2})\s+de\s+([A-Za-zçÇà-ÿÀ-Ý.]+)(?:\s+de\s+(\d{4}))?",
            text, re.IGNORECASE,
        )
        if m:
            d1, mon1, y1, d2, mon2, y2 = m.groups()
            start = _make_date(_normalize_year(y1, default_year), _resolve_month(mon1), int(d1))
            end = _make_date(_normalize_year(y2, default_year), _resolve_month(mon2), int(d2))
            return start, end

        # Same-month shorthand: "entre 08 e 13 de junho".
        m = re.search(
            r"entre\s+(\d{1,2})\s+e\s+(\d{1,2})\s+de\s+([A-Za-zçÇà-ÿÀ-Ý.]+)",
            text, re.IGNORECASE,
        )
        if m:
            d1, d2, mon = m.groups()
            month = _resolve_month(mon)
            return (
                _make_date(default_year, month, int(d1)),
                _make_date(default_year, month, int(d2)),
            )

        return None, None

    @staticmethod
    def _parse_purpose(text: str) -> str | None:
        """Purpose = the lowercase-starting clause following 'para' (the goal)."""
        match = re.search(r"\bpara\s+([a-zà-ÿ].*?)\s*\.?\s*$", text)
        return match.group(1).strip() if match else None


def parse_clarification(text: str, default_year: int) -> dict:
    """Parse a (possibly partial) clarification reply into intent fields.

    Returns a dict with keys origin / destination (Location | None) and
    start_date / end_date (date | None). Any field not mentioned stays None so
    the caller can fill only what is missing.
    """
    return {
        "origin": _clar_origin(text),
        "destination": _clar_destination(text),
        **dict(zip(("start_date", "end_date"), _clar_dates(text, default_year))),
    }


def _clar_origin(text: str) -> Location | None:
    cues = (
        r"(?:\bsaindo de\b|\bpartindo de\b|\bvou sair de\b|\bsair de\b"
        r"|\borigem\b(?:\s+é|\s*:)?|\bdesde\b|\bde\b)"
    )
    return _search_location(cues, text)


def _clar_destination(text: str) -> Location | None:
    cues = (
        r"(?:\bpara\b|\bcom destino a\b|\bdestino a\b|\bdestino\b(?:\s+é|\s*:)?"
        r"|\bindo para\b|\brumo a\b)"
    )
    return _search_location(cues, text)


def _clar_dates(text: str, default_year: int) -> tuple[date | None, date | None]:
    """Parse outbound/return dates from partial phrasings."""
    start = _clar_single_date(text, r"\b(?:ida|partida|sa[ií]da)\b", default_year)
    end = _clar_single_date(text, r"\b(?:volta|retorno|regresso)\b", default_year)

    if start is None or end is None:
        # Range form: "de 29-06 a 10-07" (or with year).
        m = re.search(
            r"\bde\s+(\d{1,2})[-/](\d{1,2})(?:[-/](\d{2,4}))?"
            r"\s+a\s+(\d{1,2})[-/](\d{1,2})(?:[-/](\d{2,4}))?",
            text, re.IGNORECASE,
        )
        if m:
            d1, mo1, y1, d2, mo2, y2 = m.groups()
            start = start or _make_date(_normalize_year(y1, default_year), int(mo1), int(d1))
            end = end or _make_date(_normalize_year(y2, default_year), int(mo2), int(d2))

    if start is None or end is None:
        # Fall back to the full-request date forms ("entre ...", month names).
        s2, e2 = TravelPlannerAgent._parse_dates(text, default_year)
        start = start or s2
        end = end or e2
    return start, end


def _clar_single_date(text: str, cue: str, default_year: int) -> date | None:
    """A single labelled date, e.g. "ida em 29-06-2026" or "volta 10 de julho"."""
    m = re.search(
        cue + r"\s+(?:em\s+|dia\s+)?(\d{1,2})[-/](\d{1,2})(?:[-/](\d{2,4}))?",
        text, re.IGNORECASE,
    )
    if m:
        day, month, year = m.groups()
        return _make_date(_normalize_year(year, default_year), int(month), int(day))
    m = re.search(
        cue + r"\s+(?:em\s+|dia\s+)?(\d{1,2})\s+de\s+([A-Za-zçÇà-ÿÀ-Ý.]+)"
        r"(?:\s+de\s+(\d{4}))?",
        text, re.IGNORECASE,
    )
    if m:
        day, mon, year = m.groups()
        return _make_date(_normalize_year(year, default_year), _resolve_month(mon), int(day))
    return None
