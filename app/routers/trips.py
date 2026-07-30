"""Trip endpoints.

Placeholder implementations for the skeleton: a TripRun is created and stored,
but the orchestrator does not yet run agents. See specs/api.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.core.dev_seed import new_seeded_run
from app.orchestrator.orchestrator import CannotAdvance, Orchestrator
from app.repositories.trip_repository import TripRepository
from app.schemas.approval import ApprovalRequest
from app.schemas.execution import RunResponse
from app.schemas.report import TravelReport
from app.schemas.trip import ClarifyRequest, TripPhase, TripRequest, TripRun

router = APIRouter(prefix="/trips", tags=["trips"])

# Skeleton-stage singletons. TODO: replace with proper dependency injection and a
# SQLite-backed repository shared across routers/orchestrator.
_trips = TripRepository()
_orchestrator = Orchestrator(trip_repository=_trips)


@router.post("", status_code=201, response_model=TripRun)
def create_trip(request: TripRequest) -> TripRun:
    """Create a trip-planning run from a natural-language request.

    In DEV_MODE the incoming payload is ignored and the run is seeded from
    DEV_TRIP (already at the UNDERSTANDING phase, ready to advance).
    """
    if get_settings().dev_mode:
        return _trips.add(new_seeded_run())
    run = TripRun(
        id=str(uuid4()),
        request_text=request.request_text,
        phase=TripPhase.CREATED,
        created_at=datetime.now(timezone.utc),
    )
    # TODO: kick off (or allow advancing) the orchestrator state machine.
    return _trips.add(run)


@router.get("", response_model=list[TripRun])
def list_trips() -> list[TripRun]:
    """List all trip runs for inspection."""
    return _trips.list()


@router.get("/{trip_id}", response_model=TripRun)
def get_trip(trip_id: str) -> TripRun:
    """Fetch the full current state of a trip run."""
    run = _trips.get(trip_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return run


@router.post("/{trip_id}/advance", response_model=TripRun)
def advance_trip(trip_id: str) -> TripRun:
    """Advance the run by one phase.

    Implemented so far: CREATED -> UNDERSTANDING -> PLANNING. Advancing past
    PLANNING is not implemented yet and returns 501.
    """
    run = _trips.get(trip_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    try:
        run = _orchestrator.advance(run)
    except CannotAdvance as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return _trips.save(run)

@router.post("/{trip_id}/clarify", response_model=TripRun)
def clarify_trip(trip_id: str, body: ClarifyRequest) -> TripRun:
    """Answer a clarification for an existing trip (does NOT create a new run)."""
    run = _trips.get(trip_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    try:
        run = _orchestrator.clarify(run, body.message)
    except CannotAdvance as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _trips.save(run)


@router.post("/{trip_id}/run", response_model=RunResponse)
def run_trip(trip_id: str) -> RunResponse:
    """Automatically advance the run until a human/terminal stop condition.

    Stops at clarification, policy block, awaiting approval, rejected, or
    completed. The step-by-step /advance endpoint remains for teaching/debug.
    """
    run = _trips.get(trip_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    summary = _orchestrator.run_until_stop(run)
    _trips.save(run)
    return RunResponse(trip=run, execution_summary=summary)


@router.post("/{trip_id}/approve", response_model=TripRun)
def approve_trip(trip_id: str, body: ApprovalRequest) -> TripRun:
    """Human-in-the-loop: approve a trip that is awaiting approval."""
    run = _trips.get(trip_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    try:
        run = _orchestrator.approve(run, body.reviewer, body.comments)
    except CannotAdvance as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _trips.save(run)


@router.post("/{trip_id}/reject", response_model=TripRun)
def reject_trip(trip_id: str, body: ApprovalRequest) -> TripRun:
    """Human-in-the-loop: reject a trip that is awaiting approval."""
    run = _trips.get(trip_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    try:
        run = _orchestrator.reject(run, body.reviewer, body.comments)
    except CannotAdvance as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _trips.save(run)

@router.get("/{trip_id}/report", response_model=TravelReport)
def get_report(trip_id: str) -> TravelReport:
    """Fetch the final travel report (only when the run is COMPLETED)."""
    run = _trips.get(trip_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    if run.phase is not TripPhase.COMPLETED or run.report is None:
        raise HTTPException(
            status_code=409,
            detail="Report is not available until the trip is COMPLETED",
        )
    return run.report

# TODO: add /run-to-gate, /flights, /hotels, /select, /steps endpoints
#       as the remaining orchestrator phases are implemented (see specs/api.md).
