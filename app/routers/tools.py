"""Tools introspection endpoint.

Lists the registered tools and their input/output schema names, demonstrating
the tool registry and provider abstraction. See specs/api.md (GET /tools).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.llm.gemini_client import llm_status
from app.schemas.location import LocationQuery, ResolvedLocation
from app.tools.location_resolver_tool import LocationResolverTool
from app.tools.registry import build_default_registry

router = APIRouter(prefix="/tools", tags=["tools"])

_registry = build_default_registry()


class LlmStatus(BaseModel):
    """Safe LLM configuration view (no API key)."""

    llm_enabled: bool
    provider: str
    model: str
    api_key_configured: bool


@router.get("/llm-status", response_model=LlmStatus)
def get_llm_status() -> LlmStatus:
    """Report whether the LLM is enabled and configured (never the key)."""
    return LlmStatus(**llm_status())


class ResolveLocationRequest(BaseModel):
    """Manual location-resolution request (debug helper)."""

    location_text: str
    full_request: Optional[str] = None


@router.post("/resolve-location", response_model=ResolvedLocation)
def resolve_location(body: ResolveLocationRequest) -> ResolvedLocation:
    """Resolve a single location via the configured provider (debug helper).

    Uses Gemini when LLM_ENABLED=true, else the offline demo provider. Errors are
    returned as a controlled ResolvedLocation (requires_clarification), never a
    raw traceback.
    """
    tool = LocationResolverTool()
    return tool.resolve(
        LocationQuery(
            location_text=body.location_text,
            city=body.location_text,
            request_text=body.full_request,
        )
    )


class ToolInfo(BaseModel):
    """Lightweight, serializable view of a registered tool."""

    name: str
    description: str
    input_schema: str | None = None
    output_schema: str | None = None
    simulated: bool = True


class ToolListResponse(BaseModel):
    tools: list[ToolInfo]


@router.get("", response_model=ToolListResponse)
def list_tools() -> ToolListResponse:
    """List the registered tools and their schemas."""
    tools = [
        ToolInfo(
            name=spec.name,
            description=spec.description,
            input_schema=spec.input_model.__name__ if spec.input_model else None,
            output_schema=spec.output_model.__name__ if spec.output_model else None,
            simulated=spec.simulated,
        )
        for spec in _registry.list()
    ]
    return ToolListResponse(tools=tools)
