"""IntentUnderstandingAgent — extracts structured trip intent from text.

Uses Gemini when LLM_ENABLED=true; otherwise (or if Gemini fails) it falls back
to the deterministic parser. It extracts textual locations only — airport codes
remain the LocationResolverTool's responsibility. See specs/agents.md.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Callable, Optional

from app.agents.base import Agent, RunContext
from app.agents.travel_planner import location_from_mention, parse_intent_deterministic
from app.core.config import Settings, get_settings
from app.llm.gemini_client import build_gemini_client
from app.llm.prompts import build_clarification_reply_prompt, build_intent_prompt
from app.schemas.intent import IntentExtraction
from app.schemas.trip import TripIntent

logger = logging.getLogger("app.agents.intent_understanding")

_EMPTY_VALUES = {"", "...", "none", "null", "n/a", "unknown"}


class IntentUnderstandingAgent(Agent):
    """Extracts a TripIntent from a natural-language request."""

    name = "IntentUnderstandingAgent"

    def __init__(
        self,
        generate: Optional[Callable[[str], str]] = None,
        use_llm: Optional[bool] = None,
    ) -> None:
        self._generate = generate  # inject for tests
        self._use_llm = use_llm  # override settings (tests)

    def understand(self, request_text: str) -> TripIntent:
        settings = get_settings()
        if self._llm_enabled(settings):
            try:
                extraction = self.extract(request_text)
                return self._to_intent(extraction)
            except Exception as exc:  # any LLM/parse failure → deterministic
                logger.warning(
                    "Gemini intent extraction failed; using deterministic parser: %s", exc
                )
        return parse_intent_deterministic(request_text, settings.default_trip_year)

    def extract(self, request_text: str) -> IntentExtraction:
        """Call the LLM and parse its JSON into an IntentExtraction."""
        raw = self._call_model(build_intent_prompt(request_text))
        data = json.loads(_extract_json(raw))
        return IntentExtraction(
            origin_text=_clean(data.get("origin_text")),
            destination_text=_clean(data.get("destination_text")),
            start_date=_coerce_date(data.get("start_date")),
            end_date=_coerce_date(data.get("end_date")),
            purpose=_clean(data.get("purpose")),
            event_name=_clean(data.get("event_name")),
            organization=_clean(data.get("organization")),
            missing_fields=list(data.get("missing_fields") or []),
            confidence=float(data.get("confidence") or 0.0),
        )

    def interpret_clarification(
        self,
        message: str,
        question: Optional[str] = None,
        intent_summary: Optional[str] = None,
    ) -> IntentExtraction:
        """Interpret a short clarification reply (e.g. "GRU", "10 a 15 de setembro").

        The pending question is passed as context so the model knows which field
        the reply answers. Only the four routable fields are filled.
        """
        raw = self._call_model(
            build_clarification_reply_prompt(message, question, intent_summary)
        )
        data = json.loads(_extract_json(raw))
        return IntentExtraction(
            origin_text=_clean(data.get("origin_text")),
            destination_text=_clean(data.get("destination_text")),
            start_date=_coerce_date(data.get("start_date")),
            end_date=_coerce_date(data.get("end_date")),
        )

    def _to_intent(self, extraction: IntentExtraction) -> TripIntent:
        return TripIntent(
            origin=location_from_mention(extraction.origin_text),
            destination=location_from_mention(extraction.destination_text),
            start_date=extraction.start_date,
            end_date=extraction.end_date,
            purpose=extraction.purpose,
            event_name=extraction.event_name,
            organization=extraction.organization,
        )

    def _llm_enabled(self, settings: Settings) -> bool:
        return self._use_llm if self._use_llm is not None else settings.llm_enabled

    def _call_model(self, prompt: str) -> str:
        if self._generate is not None:
            return self._generate(prompt)
        client = build_gemini_client()
        if client is None:
            raise RuntimeError("LLM is disabled; cannot call Gemini")
        return client.generate(prompt)

    def run(self, context: RunContext) -> TripIntent:
        return self.understand(context.get("request_text", ""))


# --- helpers --------------------------------------------------------------- #
def _clean(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return None if text.lower() in _EMPTY_VALUES else text


def _coerce_date(value) -> Optional[date]:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except (ValueError, TypeError):
        return None


def _extract_json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text
