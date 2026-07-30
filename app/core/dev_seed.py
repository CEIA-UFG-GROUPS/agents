"""Development seed scenario.

When DEV_MODE is enabled the app runs the full travel pipeline locally without
any HTTP request body, using the fixed DEV_TRIP scenario below. The seed is
injected *before* orchestration starts: it builds a fully-understood TripIntent
and places the run at the UNDERSTANDING phase, so the downstream agents
(search → rank → recommend → budget) run exactly as in the live flow.

No worker agent is modified — only the run's initial state is seeded here.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from app.schemas.trip import (
    Location,
    Step,
    TripIntent,
    TripPhase,
    TripRequest,
    TripRun,
)

DEV_TRIP = {
    "origin": {"city": "Curitiba", "airport": "CWB"},
    "destination": {"city": "Belo Horizonte", "airport": "CNF"},
    "start_date": "2026-07-20",
    "end_date": "2026-08-02",
    "purpose": "Conduzir workshops e reuniões do EnergyGPT",
}


def build_seed_intent() -> TripIntent:
    """Build the structured TripIntent from DEV_TRIP (no text parsing needed)."""
    return TripIntent(
        origin=Location(**DEV_TRIP["origin"]),
        destination=Location(**DEV_TRIP["destination"]),
        start_date=date.fromisoformat(DEV_TRIP["start_date"]),
        end_date=date.fromisoformat(DEV_TRIP["end_date"]),
        purpose=DEV_TRIP["purpose"],
    )


def build_seed_request() -> TripRequest:
    """The TripRequest used in DEV_MODE (incoming payloads are ignored)."""
    return TripRequest(request_text=DEV_TRIP["purpose"])


def apply_seed(run: TripRun) -> None:
    """Inject the seed intent and move the run to UNDERSTANDING.

    Records an `understand_request` step so the run looks like a normal flow,
    just with the intent provided by the seed rather than parsed from text.
    """
    intent = build_seed_intent()
    run.intent = intent
    run.phase = TripPhase.UNDERSTANDING
    run.steps.append(
        Step(
            name="understand_request",
            status="done",
            order=len(run.steps) + 1,
            input=run.request_text,
            output=intent.model_dump(mode="json"),
        )
    )


def new_seeded_run() -> TripRun:
    """Create a fresh TripRun already seeded and ready to advance."""
    run = TripRun(
        id=str(uuid4()),
        request_text=DEV_TRIP["purpose"],
        phase=TripPhase.CREATED,
        created_at=datetime.now(timezone.utc),
    )
    apply_seed(run)
    return run


def diagnostics_banner() -> str:
    """The startup banner printed in DEV_MODE."""
    line = "=" * 50
    return "\n".join(
        [
            line,
            "TRAVEL PLANNER - DEVELOPMENT MODE",
            line,
            f"Origin: {DEV_TRIP['origin']['city']} ({DEV_TRIP['origin']['airport']})",
            f"Destination: {DEV_TRIP['destination']['city']} ({DEV_TRIP['destination']['airport']})",
            f"Departure: {DEV_TRIP['start_date']}",
            f"Return: {DEV_TRIP['end_date']}",
            f"Purpose: {DEV_TRIP['purpose']}",
            line,
        ]
    )
