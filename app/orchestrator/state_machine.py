"""Trip-run state machine.

Defines the ordered phase transitions. The only transition requiring an external
(human) event is AWAITING_APPROVAL -> GENERATING_REPORT, gated on an approved
decision. See specs/architecture.md §3.
"""

from __future__ import annotations

from app.schemas.trip import TripPhase

# Linear "happy path" of automatic transitions up to the approval gate.
NEXT_PHASE: dict[TripPhase, TripPhase] = {
    TripPhase.CREATED: TripPhase.UNDERSTANDING,
    TripPhase.UNDERSTANDING: TripPhase.PLANNING,
    TripPhase.PLANNING: TripPhase.RETRIEVING_MEMORY,
    TripPhase.RETRIEVING_MEMORY: TripPhase.RESOLVING_LOCATIONS,
    TripPhase.RESOLVING_LOCATIONS: TripPhase.SEARCHING_FLIGHTS,
    TripPhase.SEARCHING_FLIGHTS: TripPhase.SEARCHING_HOTELS,
    TripPhase.SEARCHING_HOTELS: TripPhase.RANKING_FLIGHTS,
    TripPhase.RANKING_FLIGHTS: TripPhase.RANKING_HOTELS,
    TripPhase.RANKING_HOTELS: TripPhase.RECOMMENDING,
    TripPhase.RECOMMENDING: TripPhase.ESTIMATING_BUDGET,
    TripPhase.ESTIMATING_BUDGET: TripPhase.VALIDATING_POLICY,
    TripPhase.VALIDATING_POLICY: TripPhase.AWAITING_APPROVAL,
    # AWAITING_APPROVAL is a gate: it advances to GENERATING_REPORT only when the
    # approval decision is "approved" (enforced by the orchestrator).
    TripPhase.AWAITING_APPROVAL: TripPhase.GENERATING_REPORT,
    TripPhase.GENERATING_REPORT: TripPhase.COMPLETED,
}

# Phases at which the run halts and waits for an external event/result.
GATE_PHASES = {TripPhase.AWAITING_APPROVAL}

# Terminal phases.
TERMINAL_PHASES = {TripPhase.COMPLETED, TripPhase.REJECTED}


def next_phase(current: TripPhase) -> TripPhase | None:
    """Return the next automatic phase, or None at a gate/terminal phase."""
    return NEXT_PHASE.get(current)


def can_advance(current: TripPhase) -> bool:
    """True if the run can advance automatically from `current`."""
    return current in NEXT_PHASE and current not in GATE_PHASES
