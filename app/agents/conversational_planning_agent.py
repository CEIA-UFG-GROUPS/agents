"""ConversationalPlanningAgent — multi-turn trip planning.

Wraps the deterministic create → clarify → run flow into a conversation:

- keeps ONE active trip per session (preserves trip_id),
- never creates a new trip while a trip is awaiting clarification,
- asks ONE focused question per turn and interprets short answers
  (e.g. "San Jose", "California", "29/06 a 10/07"),
- continues the workflow automatically once all fields are resolved.

It does not change the orchestrator or other agents. See specs/agents.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel

from app.agents.base import Agent, RunContext
from app.agents.clarification_agent import ClarificationAgent
from app.agents.location_understanding_agent import _missing_required_fields
from app.agents.travel_planner import parse_clarification
from app.core.config import get_settings
from app.orchestrator.orchestrator import Orchestrator
from app.orchestrator.state_machine import TERMINAL_PHASES
from app.repositories.trip_repository import TripRepository
from app.schemas.trip import TripPhase, TripRun


class ConversationTurn(BaseModel):
    """The agent's response for one user message."""

    trip_id: str
    reply: str
    requires_clarification: bool
    phase: str
    stop_reason: Optional[str] = None
    done: bool = False


class _Pending(BaseModel):
    """What the agent last asked for (used to interpret the next answer)."""

    kind: str = "none"  # "destination" | "origin" | "dates" | "none"
    ambiguous: bool = False
    city: Optional[str] = None
    fields: list[str] = []


class ConversationalPlanningAgent(Agent):
    """Drives a multi-turn planning conversation over a single trip."""

    name = "ConversationalPlanningAgent"

    def __init__(
        self,
        trip_repository: Optional[TripRepository] = None,
        orchestrator: Optional[Orchestrator] = None,
        clarification_agent: Optional[ClarificationAgent] = None,
    ) -> None:
        self.repository = trip_repository or TripRepository()
        self.orchestrator = orchestrator or Orchestrator(trip_repository=self.repository)
        self.clarification_agent = clarification_agent or ClarificationAgent()
        self.active_trip_id: Optional[str] = None
        self._pending = _Pending()

    def handle(self, message: str) -> ConversationTurn:
        run = self._active_run()

        if run is None or run.phase in TERMINAL_PHASES:
            # No active trip (or the previous one finished) → start a new trip.
            run = self._create(message)
        elif run.requires_clarification:
            # Active trip waiting on info → answer it on the SAME trip.
            self.orchestrator.clarify(run, self._effective_message(run, message))
        else:
            # Mid-flight and nothing is being asked.
            return ConversationTurn(
                trip_id=run.id,
                reply="Já existe uma viagem em andamento. Posso continuar quando você quiser.",
                requires_clarification=False,
                phase=run.phase.value,
            )

        summary = self.orchestrator.run_until_stop(run)
        self.repository.save(run)
        self.active_trip_id = run.id
        self._pending = self._compute_pending(run)

        return ConversationTurn(
            trip_id=run.id,
            reply=self._reply(run, summary.stop_reason),
            requires_clarification=run.requires_clarification,
            phase=run.phase.value,
            stop_reason=summary.stop_reason,
            done=run.phase in TERMINAL_PHASES,
        )

    def run(self, context: RunContext) -> ConversationTurn:
        return self.handle(context.get("message", ""))

    # --- internals -------------------------------------------------------
    def _active_run(self) -> Optional[TripRun]:
        return self.repository.get(self.active_trip_id) if self.active_trip_id else None

    def _create(self, message: str) -> TripRun:
        run = TripRun(
            id=str(uuid4()),
            request_text=message,
            phase=TripPhase.CREATED,
            created_at=datetime.now(timezone.utc),
        )
        self._pending = _Pending()
        return self.repository.add(run)

    def _effective_message(self, run: TripRun, message: str) -> str:
        """Turn a short answer into a message the clarify parser understands."""
        year = get_settings().default_trip_year
        parsed = parse_clarification(message, year)
        pending = self._pending

        if pending.kind == "destination" and parsed["destination"] is None:
            if pending.ambiguous and pending.city:
                return f"o destino é {pending.city}, {message}"
            return f"o destino é {message}"

        if pending.kind == "origin" and parsed["origin"] is None:
            if pending.ambiguous and pending.city:
                return f"a origem é {pending.city}, {message}"
            return f"a origem é {message}"

        if pending.kind == "dates" and not (parsed["start_date"] or parsed["end_date"]):
            for candidate in (f"de {message}", f"entre {message}"):
                trial = parse_clarification(candidate, year)
                if trial["start_date"] or trial["end_date"]:
                    return candidate

        return message

    def _compute_pending(self, run: TripRun) -> _Pending:
        if not run.requires_clarification:
            return _Pending()
        question = run.clarification_question or ""
        if question.startswith("Você deseja"):
            return _Pending(kind="destination", ambiguous=True, city=_dest_city(run))
        if question.startswith("De onde"):
            return _Pending(kind="origin", ambiguous=True, city=_origin_city(run))

        missing = _missing_required_fields(run.intent)
        if "destination_airport" in missing:
            return _Pending(kind="destination", fields=["destination_airport"], city=_dest_city(run))
        dates = [f for f in ("start_date", "end_date") if f in missing]
        if dates:
            return _Pending(kind="dates", fields=dates)
        if "origin_airport" in missing:
            return _Pending(kind="origin", fields=["origin_airport"])
        return _Pending()

    def _reply(self, run: TripRun, stop_reason: Optional[str]) -> str:
        if run.requires_clarification:
            pending = self._pending
            if pending.ambiguous:
                return run.clarification_question or "Pode esclarecer, por favor?"
            if pending.kind in ("destination", "origin"):
                key = f"{pending.kind}_airport"
                return self.clarification_agent.clarify([key]).question
            if pending.kind == "dates":
                return self.clarification_agent.clarify(pending.fields).question
            return run.clarification_question or "Preciso de mais algumas informações."

        if stop_reason == "completed":
            return "Viagem concluída. Relatório disponível."
        if stop_reason == "policy_block":
            return "A viagem foi bloqueada pela política corporativa."
        if stop_reason == "rejected":
            return "A viagem foi rejeitada."
        # awaiting_approval (everything resolved)
        return "Entendido. A viagem está pronta para aprovação."


def _dest_city(run: TripRun) -> Optional[str]:
    return run.intent.destination.city if (run.intent and run.intent.destination) else None


def _origin_city(run: TripRun) -> Optional[str]:
    return run.intent.origin.city if (run.intent and run.intent.origin) else None
