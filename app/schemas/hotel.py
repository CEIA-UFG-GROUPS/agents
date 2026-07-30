"""Hotel search schemas (provider-agnostic). See specs/tools.md."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class HotelSearchInput(BaseModel):
    """Provider-agnostic hotel query."""

    destination: str
    check_in: date
    check_out: date
    guests: int = 1
    max_nightly_rate: Optional[float] = None
    # Traveler's preferred chain (from memory), passed through for the provider.
    preferred_chain: Optional[str] = None


class HotelOption(BaseModel):
    """A single candidate hotel returned by a hotel provider."""

    id: str
    provider: str
    # Which tool surfaced this option (e.g. "hotel_search_tool"); stamped by the
    # tool itself for observability. Default "" until a tool sets it.
    source_tool: str = ""
    hotel_name: str
    chain: str
    address: Optional[str] = None
    stars: float = 0.0
    distance_km: float = 0.0
    nightly_rate: float = 0.0
    nights: int = 1
    total_price: float = 0.0
    currency: str = "BRL"
    simulated: bool = True
    # Explainability: does this hotel's chain match the traveler's preferred
    # chain (from memory)? Set by HotelSearchAgent; does not affect ordering.
    preferred_match: bool = False


class HotelSearchResult(BaseModel):
    """Result wrapper returned by the hotel tool."""

    options: list[HotelOption] = Field(default_factory=list)
