"""Prompt templates for the LLM (Gemini) integration."""

from __future__ import annotations

from app.schemas.location import LocationQuery

# The model must return ONLY this JSON object.
_JSON_TEMPLATE = """{
  "location_text": "...",
  "city": "...",
  "region": "...",
  "country": "...",
  "airport": "...",
  "airport_name": "...",
  "confidence": 0.0,
  "is_ambiguous": false,
  "alternatives": [
    {
      "city": "...",
      "region": "...",
      "country": "...",
      "airport": "...",
      "airport_name": "..."
    }
  ],
  "reason": "..."
}"""

_INSTRUCTIONS = (
    "You are a corporate-travel location resolver. Given the full user request, "
    "the current parsed intent, and ONE location mention, identify the single "
    "most likely commercial airport for corporate travel.\n"
    "Rules: airport must be a 3-letter IATA code. If the location could refer to "
    "more than one well-known city/airport, set is_ambiguous=true and list the "
    "candidates in alternatives. Set confidence in [0,1]."
)


# --- intent extraction ----------------------------------------------------- #
_INTENT_JSON_TEMPLATE = """{
  "origin_text": "...",
  "destination_text": "...",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "purpose": "...",
  "event_name": "...",
  "organization": "...",
  "missing_fields": [],
  "confidence": 0.0
}"""

_INTENT_INSTRUCTIONS = (
    "You extract structured corporate-travel intent from a natural-language "
    "request (Portuguese or English).\n"
    "Extract: origin mention, destination mention (KEEP the region/state when "
    "given, e.g. \"San Jose, California\"), start_date, end_date, purpose, and "
    "event_name + organization if an event is mentioned.\n"
    "Rules:\n"
    "- Dates MUST be ISO YYYY-MM-DD. If the year is missing, assume 2026.\n"
    "- Do NOT resolve airport codes (that is done elsewhere).\n"
    "- If a field is unclear, leave it empty and add its name to missing_fields.\n"
    "- Never invent values. Set confidence in [0,1]."
)


def build_intent_prompt(request_text: str) -> str:
    """Build the Gemini prompt for extracting trip intent from text."""
    return "\n".join(
        [
            _INTENT_INSTRUCTIONS,
            "",
            f"REQUEST: {request_text}",
            "",
            "Return ONLY this JSON (no markdown, no commentary):",
            _INTENT_JSON_TEMPLATE,
        ]
    )


# --- clarification replies -------------------------------------------------- #
# NOTE: this reads the user's ANSWER. The prompt that phrases the QUESTION is
# _CLARIFICATION_INSTRUCTIONS / build_clarification_prompt further below.
_CLARIFICATION_REPLY_JSON_TEMPLATE = """{
  "origin_text": "...",
  "destination_text": "...",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD"
}"""

_CLARIFICATION_REPLY_INSTRUCTIONS = (
    "You interpret a SHORT reply to a clarification question in a corporate-travel "
    "conversation (Portuguese or English). The reply is usually just the answer, "
    "with no full sentence — e.g. \"GRU\", \"Recife\", \"10 a 15 de setembro\".\n"
    "Rules:\n"
    "- Use the QUESTION to decide which field the reply answers. If the question "
    "asks for the origin, a bare city/airport is the ORIGIN, not the destination.\n"
    "- Keep an airport code the user gave, e.g. \"São Paulo (GRU)\" or \"GRU\".\n"
    "- Dates MUST be ISO YYYY-MM-DD. If the year is missing, assume 2026.\n"
    "- Leave a field empty when the reply says nothing about it. Never invent values."
)


def build_clarification_reply_prompt(
    message: str,
    question: str | None = None,
    intent_summary: str | None = None,
) -> str:
    """Build the Gemini prompt that interprets a clarification reply."""
    return "\n".join(
        [
            _CLARIFICATION_REPLY_INSTRUCTIONS,
            "",
            f"QUESTION ASKED: {question or '(none)'}",
            f"KNOWN SO FAR: {intent_summary or '(nothing)'}",
            f"USER REPLY: {message}",
            "",
            "Return ONLY this JSON (no markdown, no commentary):",
            _CLARIFICATION_REPLY_JSON_TEMPLATE,
        ]
    )


# --- memory summary -------------------------------------------------------- #
_MEMORY_INSTRUCTIONS = (
    "Você resume o perfil e o histórico de um viajante corporativo em português. "
    "Com base APENAS nos fatos fornecidos, escreva um resumo curto (1-2 frases), "
    "natural e objetivo. Não invente dados. Responda SOMENTE com o resumo."
)


def build_memory_prompt(facts: str) -> str:
    """Build the Gemini prompt that summarizes traveler preferences/history."""
    return "\n".join([_MEMORY_INSTRUCTIONS, "", f"FATOS: {facts}", "", "Resumo:"])


# --- executive report ------------------------------------------------------ #
_REPORT_SECTIONS = (
    "# Executive Travel Recommendation\n"
    "## Purpose\n## Recommended Itinerary\n## Cost Summary\n"
    "## Policy Compliance\n## Approval Status\n## Final Recommendation"
)

_REPORT_INSTRUCTIONS = (
    "Você é um analista de viagens corporativas. Escreva um RELATÓRIO EXECUTIVO "
    "em Markdown, em português, claro e objetivo, com EXATAMENTE estas seções "
    "(mesmos títulos, nesta ordem):\n"
    f"{_REPORT_SECTIONS}\n\n"
    "Use APENAS os fatos fornecidos; não invente dados. Mantenha conciso "
    "(adequado para executivos). Responda SOMENTE com o Markdown."
)


def build_executive_report_prompt(facts: str) -> str:
    """Build the Gemini (Pro) prompt for the executive travel report."""
    return "\n".join([_REPORT_INSTRUCTIONS, "", "FATOS:", facts])


# --- clarification phrasing ------------------------------------------------ #
_CLARIFICATION_INSTRUCTIONS = (
    "Você é um assistente de viagens corporativas. Com base APENAS nos fatos "
    "fornecidos (campos faltando ou opções ambíguas), gere UMA pergunta curta, "
    "natural e educada, em português, para pedir a informação ao usuário.\n"
    "Regras: não invente dados; não peça nada além do necessário; se houver "
    "opções ambíguas, liste exatamente as opções fornecidas. "
    "Responda SOMENTE com a pergunta (uma linha, sem aspas)."
)


def build_clarification_prompt(facts: str) -> str:
    """Build the Gemini prompt that phrases a clarification question."""
    return "\n".join([_CLARIFICATION_INSTRUCTIONS, "", f"FATOS: {facts}", "", "Pergunta:"])


def build_location_prompt(query: LocationQuery) -> str:
    """Build the Gemini prompt for resolving one location mention."""
    base = query.location_text or query.city or query.free_text or ""
    mention = ", ".join(p for p in (base, query.region, query.country) if p)
    return "\n".join(
        [
            _INSTRUCTIONS,
            "",
            f"FULL_REQUEST: {query.request_text or ''}",
            f"CURRENT_INTENT: {query.intent_summary or ''}",
            f"LOCATION_MENTION: {mention}",
            "",
            "Return ONLY this JSON (no markdown, no commentary):",
            _JSON_TEMPLATE,
        ]
    )
