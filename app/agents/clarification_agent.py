"""ClarificationAgent — phrases natural clarification questions.

Business rules stay deterministic: the CALLER decides which fields are missing
and whether a place is ambiguous. This agent only turns those facts into a
natural Portuguese question — using Gemini when LLM_ENABLED=true, with a
deterministic fallback (also used when Gemini is off or fails). See specs/agents.md.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from pydantic import BaseModel

from app.agents.base import Agent, RunContext
from app.core.config import Settings, get_settings
from app.llm.gemini_client import build_gemini_client
from app.llm.prompts import build_clarification_prompt
from app.schemas.location import AirportOption

logger = logging.getLogger("app.agents.clarification")

# Human-readable labels for the fields required before SEARCHING_FLIGHTS.
FIELD_LABELS = {
    "origin_airport": "aeroporto de origem",
    "destination_airport": "aeroporto de destino",
    "start_date": "data de ida",
    "end_date": "data de volta",
}

# (side, options) — an ambiguous origin/destination with candidate airports.
Ambiguity = tuple[str, list[AirportOption]]


class ClarificationResult(BaseModel):
    requires_clarification: bool
    question: Optional[str] = None


class ClarificationAgent(Agent):
    """Generates a clarification question from deterministic 'need' facts."""

    name = "ClarificationAgent"

    def __init__(
        self,
        generate: Optional[Callable[[str], str]] = None,
        use_llm: Optional[bool] = None,
    ) -> None:
        self._generate = generate  # inject for tests
        self._use_llm = use_llm  # override settings (tests)

    def clarify(
        self,
        missing: list[str],
        ambiguous: Optional[Ambiguity] = None,
    ) -> ClarificationResult:
        # Deterministic decision: clarification is required iff something is
        # missing or ambiguous.
        if not missing and not ambiguous:
            return ClarificationResult(requires_clarification=False, question=None)

        question = _deterministic_question(missing, ambiguous)
        if self._llm_enabled(get_settings()):
            try:
                phrased = self._phrase_with_gemini(missing, ambiguous)
                if phrased:
                    question = phrased
            except Exception as exc:  # keep the deterministic question
                logger.warning("Gemini clarification phrasing failed; using fallback: %s", exc)

        return ClarificationResult(requires_clarification=True, question=question)

    def _phrase_with_gemini(
        self, missing: list[str], ambiguous: Optional[Ambiguity]
    ) -> Optional[str]:
        prompt = build_clarification_prompt(_facts(missing, ambiguous))
        raw = self._call_model(prompt)
        if not raw:
            return None
        # Take the first non-empty line, trimmed of quotes/markdown.
        for line in raw.splitlines():
            text = line.strip().strip('"').strip("`").strip()
            if text:
                return text
        return None

    def _llm_enabled(self, settings: Settings) -> bool:
        return self._use_llm if self._use_llm is not None else settings.llm_enabled

    def _call_model(self, prompt: str) -> str:
        if self._generate is not None:
            return self._generate(prompt)
        client = build_gemini_client()
        if client is None:
            raise RuntimeError("LLM is disabled; cannot call Gemini")
        return client.generate(prompt)

    def run(self, context: RunContext) -> ClarificationResult:
        return self.clarify(context.get("missing", []), context.get("ambiguous"))


# --- deterministic phrasing + facts --------------------------------------- #
def _deterministic_question(missing: list[str], ambiguous: Optional[Ambiguity]) -> str:
    if ambiguous:
        side, options = ambiguous
        listed = _join_or([_option_label(o) for o in options])
        if side == "origin":
            return f"De onde você deseja partir: {listed}?"
        return f"Você deseja viajar para {listed}?"

    chosen = set(missing)
    if chosen == {"destination_airport"}:
        return "Qual é o destino da viagem?"
    if chosen == {"origin_airport"}:
        return "Qual é a origem da viagem?"
    if chosen == {"start_date", "end_date"}:
        return "Quais são as datas de ida e volta?"
    if chosen == {"start_date"}:
        return "Qual é a data de ida?"
    if chosen == {"end_date"}:
        return "Qual é a data de volta?"

    labels = [FIELD_LABELS[key] for key in missing if key in FIELD_LABELS]
    return "Preciso de algumas informações para continuar: " + _join_e(labels) + "."


def _facts(missing: list[str], ambiguous: Optional[Ambiguity]) -> str:
    if ambiguous:
        side, options = ambiguous
        opts = "; ".join(_option_label(o) for o in options)
        kind = "origem" if side == "origin" else "destino"
        return f"{kind.capitalize()} ambíguo. Opções: {opts}"
    labels = [FIELD_LABELS[key] for key in missing if key in FIELD_LABELS]
    return "Campos faltando: " + ", ".join(labels)


def _option_label(option: AirportOption) -> str:
    return f"{option.city}, {option.region or option.country} ({option.airport})"


def _join_or(items: list[str]) -> str:
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " ou " + items[-1]


def _join_e(items: list[str]) -> str:
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " e " + items[-1]
