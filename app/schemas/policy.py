"""Travel policy schemas. See specs/tools.md (policy_tool)."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """A single policy finding."""

    rule_id: str
    severity: Literal["pass", "info", "warn", "block"]
    message: str


class PolicyInput(BaseModel):
    """Inputs the policy tool evaluates (loose typing to avoid coupling)."""

    intent: Optional[Any] = None
    flight: Optional[Any] = None
    hotel: Optional[Any] = None
    budget: Optional[Any] = None


class PolicyResult(BaseModel):
    """Outcome of policy validation."""

    status: Literal["pass", "warn", "block"] = "pass"
    findings: list[Finding] = Field(default_factory=list)
    requires_human_approval: bool = False
