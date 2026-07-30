"""Schema for LLM-extracted trip intent (textual — no airport codes)."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class IntentExtraction(BaseModel):
    """Structured intent extracted from natural language by the LLM.

    Locations are kept as text (origin_text / destination_text). Airport codes
    are NOT resolved here — that stays with the LocationResolverTool.
    """

    origin_text: Optional[str] = None
    destination_text: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    purpose: Optional[str] = None
    event_name: Optional[str] = None
    organization: Optional[str] = None
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = 0.0
