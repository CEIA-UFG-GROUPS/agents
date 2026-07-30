"""Offline demo location resolver — FALLBACK / TESTING ONLY.

⚠️  This provider contains a tiny, hardcoded city→airport map. It exists ONLY so
the demo runs deterministically and offline when LLM_ENABLED=false. It is NOT a
real airport database and must not be used in production. The Gemini provider is
the real resolver.
"""

from __future__ import annotations

import unicodedata

from app.schemas.location import AirportOption, LocationQuery, ResolvedLocation
from app.tools.providers.location_resolver_provider import LocationResolverProvider

# DEMO-ONLY unambiguous cities (keys are accent-stripped, lowercase).
_DEMO_AIRPORTS: dict[str, tuple[str, str, str]] = {
    # city_key: (airport, airport_name, country)
    "curitiba": ("CWB", "Afonso Pena International", "Brazil"),
    "belo horizonte": ("CNF", "Tancredo Neves International", "Brazil"),
    "goiania": ("GYN", "Santa Genoveva", "Brazil"),
    "sao paulo": ("GRU", "Guarulhos International", "Brazil"),
    "rio de janeiro": ("GIG", "Galeão International", "Brazil"),
}

# DEMO-ONLY ambiguous cities → resolved only when a region/country is given.
_AMBIGUOUS: dict[str, list[AirportOption]] = {
    "san jose": [
        AirportOption(
            airport="SJC", airport_name="Norman Y. Mineta San José International",
            city="San Jose", region="California", country="United States",
        ),
        AirportOption(
            airport="SJO", airport_name="Juan Santamaría International",
            city="San José", region=None, country="Costa Rica",
        ),
    ],
}


def _norm(text: str) -> str:
    """Lowercase, strip accents, and flatten separators for robust matching."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = decomposed.encode("ascii", "ignore").decode().lower()
    for sep in (",", "-", "–", "/"):
        ascii_text = ascii_text.replace(sep, " ")
    return " ".join(ascii_text.split())


# US state abbreviations relevant to the demo (extend as needed).
_STATE_ABBREV = {"ca": "california"}


def _option_matches(option: AirportOption, disambig: str) -> bool:
    """Does a region/country qualifier point at this option?

    Matches a full word, a prefix of region/country (so "ca" -> "california"
    but not "costa rica"), or a known state abbreviation.
    """
    expanded = _STATE_ABBREV.get(disambig, disambig)
    for field in (option.region, option.country):
        norm = _norm(field or "")
        if not norm:
            continue
        words = norm.split()
        if (
            norm.startswith(disambig)
            or norm.startswith(expanded)
            or disambig in words
            or expanded in words
        ):
            return True
    return False


class OfflineDemoLocationResolverProvider(LocationResolverProvider):
    """Resolves a small set of demo cities. Fallback/testing only."""

    name = "offline_demo"

    def resolve(self, query: LocationQuery) -> ResolvedLocation:
        raw_city = (query.city or query.free_text or "").strip()
        norm_city = _norm(raw_city)
        hint = _norm(query.region or "") or _norm(query.country or "")

        if not norm_city:
            return ResolvedLocation(requires_clarification=True, reason="no location given")

        # Unambiguous direct match.
        if norm_city in _DEMO_AIRPORTS:
            return self._known(norm_city, raw_city)

        # Ambiguous base (optionally with a trailing region token in the city).
        base, trailing = self._split_ambiguous(norm_city)
        if base in _AMBIGUOUS:
            options = _AMBIGUOUS[base]
            disambig = hint or trailing
            if disambig:
                for opt in options:
                    if _option_matches(opt, disambig):
                        return self._from_option(opt)
            return ResolvedLocation(
                city=raw_city,
                requires_clarification=True,
                reason="ambiguous city; specify region/country",
                options=options,
            )

        # Prefix match ("san jose california" without separators handled above).
        for key in _DEMO_AIRPORTS:
            if norm_city.startswith(key + " "):
                return self._known(key, raw_city)

        return ResolvedLocation(city=raw_city or None, requires_clarification=True, reason="unknown location")

    @staticmethod
    def _split_ambiguous(norm_city: str) -> tuple[str, str]:
        for key in _AMBIGUOUS:
            if norm_city == key:
                return key, ""
            if norm_city.startswith(key + " "):
                return key, norm_city[len(key):].strip()
        return norm_city, ""

    @staticmethod
    def _known(key: str, raw_city: str) -> ResolvedLocation:
        airport, name, country = _DEMO_AIRPORTS[key]
        return ResolvedLocation(
            city=raw_city, country=country, airport=airport,
            airport_name=name, confidence=0.95,
            reason="offline demo mapping",
        )

    @staticmethod
    def _from_option(opt: AirportOption) -> ResolvedLocation:
        return ResolvedLocation(
            city=opt.city, region=opt.region, country=opt.country,
            airport=opt.airport, airport_name=opt.airport_name,
            confidence=0.9, reason="offline demo mapping (disambiguated)",
        )
