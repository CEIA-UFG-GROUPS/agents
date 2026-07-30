"""Schemas for automatic workflow execution (POST /trips/{id}/run)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.trip import TripRun

StopReason = Literal[
    "awaiting_approval",
    "clarification_required",
    "completed",
    "rejected",
    "policy_block",
    "error",
]


class ExecutionSummary(BaseModel):
    """What an automatic run did and why it stopped."""

    started_phase: str
    ended_phase: str
    steps_executed: list[str] = Field(default_factory=list)
    stop_reason: StopReason


class RunResponse(BaseModel):
    """Response of POST /trips/{id}/run: final state + a summary."""

    trip: TripRun
    execution_summary: ExecutionSummary
