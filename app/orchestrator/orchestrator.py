"""Orchestrator — selects and runs the right agent for each phase.

It persists results and enforces the human approval gate. Currently the first
two phases are implemented (CREATED -> UNDERSTANDING -> PLANNING); later phases
raise NotImplementedError. See specs/architecture.md.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.agents.budget_agent import BudgetAgent
from app.agents.document_agent import DocumentAgent
from app.agents.flight_ranking_agent import FlightRankingAgent
from app.agents.flight_search_agent import FlightSearchAgent
from app.agents.hotel_ranking_agent import HotelRankingAgent
from app.agents.hotel_search_agent import HotelSearchAgent
from app.agents.location_understanding_agent import LocationUnderstandingAgent
from app.agents.memory_agent import MemoryAgent
from app.agents.policy_agent import PolicyAgent
from app.agents.travel_planner import (
    TravelPlannerAgent,
    location_from_answer,
    parse_clarification,
)
from app.agents.travel_recommendation_agent import TravelRecommendationAgent
from app.core.config import get_settings
from app.orchestrator.state_machine import TERMINAL_PHASES, next_phase
from app.schemas.approval import (
    ApprovalDecision,
    ApprovalResult,
    ApprovalStatus,
)
from app.schemas.execution import ExecutionSummary
from app.schemas.trip import Step, TripIntent, TripPhase, TripRun

logger = logging.getLogger("app.orchestrator")

# Safety cap on automatic advances (well above the real phase count).
_MAX_AUTO_STEPS = 60

# Words that signal the user is correcting an already-known field.
_CORRECTION_HINTS = ("corrig", "corret", "na verdade", "na real", "troc", "mud", "alter")


def _is_correction(message: str) -> bool:
    text = message.lower()
    return any(hint in text for hint in _CORRECTION_HINTS)


def _intent_summary(intent: TripIntent | None) -> str:
    """One-line summary of what is already known (context for the LLM)."""
    if intent is None:
        return ""
    origin = intent.origin.airport or intent.origin.city if intent.origin else None
    dest = intent.destination.airport or intent.destination.city if intent.destination else None
    return f"origin={origin}; destination={dest}; dates={intent.start_date}..{intent.end_date}"

# Maps each phase to the agent responsible for it (see specs/agents.md table).
PHASE_AGENT: dict[TripPhase, str] = {
    TripPhase.UNDERSTANDING: "TravelPlannerAgent",
    TripPhase.PLANNING: "TravelPlannerAgent",
    TripPhase.RETRIEVING_MEMORY: "MemoryAgent",
    TripPhase.RESOLVING_LOCATIONS: "LocationUnderstandingAgent",
    TripPhase.SEARCHING_FLIGHTS: "FlightSearchAgent",
    TripPhase.SEARCHING_HOTELS: "HotelSearchAgent",
    TripPhase.RANKING_FLIGHTS: "FlightRankingAgent",
    TripPhase.RANKING_HOTELS: "HotelRankingAgent",
    TripPhase.RECOMMENDING: "TravelRecommendationAgent",
    TripPhase.ESTIMATING_BUDGET: "BudgetAgent",
    TripPhase.VALIDATING_POLICY: "PolicyAgent",
    TripPhase.AWAITING_APPROVAL: "HumanApproval",
    TripPhase.GENERATING_REPORT: "DocumentAgent",
}


class CannotAdvance(Exception):
    """Raised when a run cannot advance (gate reached or terminal phase)."""


class Orchestrator:
    """Drives a TripRun through the state machine."""

    def __init__(
        self,
        trip_repository=None,
        planner: TravelPlannerAgent | None = None,
        memory_agent: MemoryAgent | None = None,
        flight_search_agent: FlightSearchAgent | None = None,
        hotel_search_agent: HotelSearchAgent | None = None,
        flight_ranking_agent: FlightRankingAgent | None = None,
        hotel_ranking_agent: HotelRankingAgent | None = None,
        travel_recommendation_agent: TravelRecommendationAgent | None = None,
        budget_agent: BudgetAgent | None = None,
        policy_agent: PolicyAgent | None = None,
        document_agent: DocumentAgent | None = None,
        location_understanding_agent: LocationUnderstandingAgent | None = None,
        intent_understanding_agent=None,
    ) -> None:
        # TODO: inject the remaining repositories, tool registry, and agents.
        self.trip_repository = trip_repository
        self.planner = planner or TravelPlannerAgent()
        self.memory_agent = memory_agent or MemoryAgent()
        self.location_understanding_agent = (
            location_understanding_agent or LocationUnderstandingAgent()
        )
        self.flight_search_agent = flight_search_agent or FlightSearchAgent()
        self.hotel_search_agent = hotel_search_agent or HotelSearchAgent()
        self.flight_ranking_agent = flight_ranking_agent or FlightRankingAgent()
        self.hotel_ranking_agent = hotel_ranking_agent or HotelRankingAgent()
        self.travel_recommendation_agent = (
            travel_recommendation_agent or TravelRecommendationAgent()
        )
        self.budget_agent = budget_agent or BudgetAgent()
        self.policy_agent = policy_agent or PolicyAgent()
        self.document_agent = document_agent or DocumentAgent()
        # Built lazily on the first clarification (see _intent_agent).
        self._intent_understanding_agent = intent_understanding_agent

    def advance(self, run: TripRun) -> TripRun:
        """Run the next phase's work and move the run into that phase.

        Implemented phases: UNDERSTANDING (parse intent), PLANNING (build the
        explicit plan), RETRIEVING_MEMORY (load preferences + enrich the
        origin), RESOLVING_LOCATIONS (resolve airports + validate required
        fields), SEARCHING_FLIGHTS (query the flight tools), and SEARCHING_HOTELS
        (query the hotel tool), RANKING_FLIGHTS (score flights), and
        RANKING_HOTELS (score hotels), RECOMMENDING (consolidate the picks), and
        ESTIMATING_BUDGET (total the trip cost), and VALIDATING_POLICY (check
        corporate policy), AWAITING_APPROVAL (open a pending human approval), and
        GENERATING_REPORT (build the report for an approved trip → COMPLETED).
        """
        if run.phase in TERMINAL_PHASES:
            raise CannotAdvance(f"Run is in terminal phase {run.phase.value}")

        # Clarification guard: if memory flagged an unresolved question (e.g. a
        # missing origin it could not infer), hold at RETRIEVING_MEMORY and
        # return the run unchanged until the question is answered. No
        # clarification-answer endpoint exists yet.
        if run.requires_clarification:
            return run

        # Policy-block guard: a blocking policy result halts the run at
        # VALIDATING_POLICY — it must not advance to approval. The block stays
        # visible on run.policy_result.
        if run.policy_result is not None and run.policy_result.status == "block":
            raise CannotAdvance(
                "Trip is blocked by corporate travel policy; cannot proceed to approval"
            )

        if run.phase is TripPhase.AWAITING_APPROVAL:
            # Human-in-the-loop gate: only an approved decision proceeds.
            upcoming = self._approval_gate_next(run)
        else:
            upcoming = next_phase(run.phase)
            if upcoming is None:
                raise CannotAdvance(
                    f"Run is at the {run.phase.value} gate and needs an external event"
                )

        if upcoming is TripPhase.UNDERSTANDING:
            intent = self.planner.understand(run.request_text)
            run.intent = intent
            run.phase = TripPhase.UNDERSTANDING
            self._record_step(run, "understand_request", run.request_text, intent)
        elif upcoming is TripPhase.PLANNING:
            plan = self.planner.plan(run.intent)
            run.plan = plan
            run.phase = TripPhase.PLANNING
            self._record_step(run, "create_plan", run.intent, plan)
        elif upcoming is TripPhase.RETRIEVING_MEMORY:
            intent_before = run.intent.model_copy(deep=True) if run.intent else None
            items = self.memory_agent.retrieve()
            result = self.memory_agent.enrich(run.intent, items)
            run.intent = result.intent
            run.requires_clarification = result.requires_clarification
            run.clarification_question = result.clarification_question
            run.phase = TripPhase.RETRIEVING_MEMORY
            output = {
                "memory_items": [item.model_dump(mode="json") for item in items],
                "enriched_intent": result.intent.model_dump(mode="json"),
                "requires_clarification": result.requires_clarification,
                "clarification_question": result.clarification_question,
            }
            self._record_step(run, "retrieve_memory", intent_before, output)
        elif upcoming is TripPhase.RESOLVING_LOCATIONS:
            run.phase = TripPhase.RESOLVING_LOCATIONS
            result = self.location_understanding_agent.understand(run.request_text, run.intent)
            run.intent = result.intent
            run.requires_clarification = result.requires_clarification
            run.clarification_question = result.clarification_question
            output = {
                "intent": run.intent.model_dump(mode="json") if run.intent else None,
                "requires_clarification": run.requires_clarification,
                "clarification_question": run.clarification_question,
                "resolver_notes": result.notes,
            }
            self._record_step(run, "resolve_locations", run.intent, output)
        elif upcoming is TripPhase.SEARCHING_FLIGHTS:
            options, tool_calls = self.flight_search_agent.search_with_trace(run.intent)
            run.flight_options = options
            run.phase = TripPhase.SEARCHING_FLIGHTS
            output = {
                "flight_options": [option.model_dump(mode="json") for option in options],
                "tool_calls": tool_calls,
            }
            self._record_step(run, "search_flights", run.intent, output)
        elif upcoming is TripPhase.SEARCHING_HOTELS:
            options, trace = self.hotel_search_agent.search_with_trace(run.intent)
            run.hotel_options = options
            run.phase = TripPhase.SEARCHING_HOTELS
            output = {
                "hotel_options": [option.model_dump(mode="json") for option in options],
                **trace,
            }
            self._record_step(run, "search_hotels", run.intent, output)
        elif upcoming is TripPhase.RANKING_FLIGHTS:
            preferences = {
                item.key: item.content for item in self.memory_agent.repository.all()
            }
            ranking = self.flight_ranking_agent.rank(run.flight_options, preferences)
            run.flight_ranking = ranking
            run.phase = TripPhase.RANKING_FLIGHTS
            step_input = {
                "num_flight_options": len(run.flight_options),
                "preferences_applied": preferences,
            }
            self._record_step(run, "rank_flights", step_input, ranking.model_dump(mode="json"))
        elif upcoming is TripPhase.RANKING_HOTELS:
            preferences = {
                item.key: item.content for item in self.memory_agent.repository.all()
            }
            hotel_prefs_applied = {}
            if preferences.get("preferred_hotel_chain"):
                hotel_prefs_applied["preferred_hotel_chain"] = preferences["preferred_hotel_chain"]
            result = self.hotel_ranking_agent.rank(run.hotel_options, hotel_prefs_applied)
            run.recommended_hotel = result.recommended_hotel
            run.hotel_ranking = result.hotel_ranking
            run.phase = TripPhase.RANKING_HOTELS
            step_input = {
                "num_hotel_options": len(run.hotel_options),
                "hotel_preferences_applied": hotel_prefs_applied,
            }
            self._record_step(run, "rank_hotels", step_input, result.model_dump(mode="json"))
        elif upcoming is TripPhase.RECOMMENDING:
            recommended_trip = self.travel_recommendation_agent.recommend(
                recommended_flight=(
                    run.flight_ranking.recommended_flight if run.flight_ranking else None
                ),
                recommended_hotel=run.recommended_hotel,
                flight_ranking=run.flight_ranking.ranking if run.flight_ranking else [],
                hotel_ranking=run.hotel_ranking,
                intent=run.intent,
            )
            run.recommended_trip = recommended_trip
            run.phase = TripPhase.RECOMMENDING
            output = {"recommended_trip": recommended_trip.model_dump(mode="json")}
            self._record_step(run, "recommend_trip", run.intent, output)
        elif upcoming is TripPhase.ESTIMATING_BUDGET:
            budget = self.budget_agent.estimate(
                recommended_flight=(
                    run.flight_ranking.recommended_flight if run.flight_ranking else None
                ),
                recommended_hotel=run.recommended_hotel,
                intent=run.intent,
            )
            run.budget_estimate = budget
            run.phase = TripPhase.ESTIMATING_BUDGET
            output = {"budget_estimate": budget.model_dump(mode="json")}
            self._record_step(run, "estimate_budget", run.intent, output)
        elif upcoming is TripPhase.VALIDATING_POLICY:
            policy_result = self.policy_agent.validate(
                intent=run.intent,
                recommended_flight=(
                    run.flight_ranking.recommended_flight if run.flight_ranking else None
                ),
                recommended_hotel=run.recommended_hotel,
                budget_estimate=run.budget_estimate,
            )
            run.policy_result = policy_result
            run.phase = TripPhase.VALIDATING_POLICY
            output = {"policy_result": policy_result.model_dump(mode="json")}
            self._record_step(run, "validate_policy", run.intent, output)
        elif upcoming is TripPhase.AWAITING_APPROVAL:
            # Policy passed/warned (block is guarded above): open a pending
            # approval awaiting a human decision.
            requires = (
                run.policy_result.requires_human_approval
                if run.policy_result is not None
                else True
            )
            run.approval_result = ApprovalResult(
                status=ApprovalStatus.PENDING,
                requires_human_approval=requires,
                decision=None,
            )
            run.phase = TripPhase.AWAITING_APPROVAL
            output = {"approval_result": run.approval_result.model_dump(mode="json")}
            self._record_step(run, "wait_for_approval", run.intent, output)
        elif upcoming is TripPhase.GENERATING_REPORT:
            # Reached only for an approved trip (the gate enforces it). Build the
            # report from existing data and complete the run.
            report = self.document_agent.generate(
                intent=run.intent,
                recommended_flight=(
                    run.flight_ranking.recommended_flight if run.flight_ranking else None
                ),
                recommended_hotel=run.recommended_hotel,
                recommended_trip=run.recommended_trip,
                budget_estimate=run.budget_estimate,
                policy_result=run.policy_result,
                approval_result=run.approval_result,
            )
            if report is None:
                raise CannotAdvance("Report can only be generated for an approved trip")
            run.report = report
            run.phase = TripPhase.COMPLETED
            output = {"report": report.model_dump(mode="json")}
            self._record_step(run, "generate_report", run.intent, output)
        else:
            # GENERATING_REPORT and beyond are not implemented yet.
            raise NotImplementedError(
                f"Phase {upcoming.value} is not implemented yet"
            )

        return run

    # --- automatic execution --------------------------------------------

    def run_until_stop(self, run: TripRun) -> ExecutionSummary:
        """Advance repeatedly until a human/terminal stop condition is reached.

        Stops at: clarification required, policy block, awaiting approval,
        rejected, completed, or an unexpected error. Mutates `run` in place and
        returns a summary of what happened.
        """
        started_phase = run.phase.value
        steps_before = len(run.steps)
        reason = None
        for _ in range(_MAX_AUTO_STEPS):
            reason = self._stop_reason(run)
            if reason is not None:
                break
            before = run.phase
            try:
                self.advance(run)
            except CannotAdvance:
                reason = self._stop_reason(run) or "error"
                break
            except NotImplementedError:
                reason = "error"
                break
            except Exception as exc:  # safety net: never crash the run with a 500
                logger.warning("Auto-run stopped on unexpected error: %s", exc)
                reason = "error"
                break
            if run.phase == before and not run.requires_clarification:
                reason = "error"  # no progress — avoid an infinite loop
                break
        return ExecutionSummary(
            started_phase=started_phase,
            ended_phase=run.phase.value,
            steps_executed=[s.name for s in run.steps[steps_before:]],
            stop_reason=reason or "error",
        )

    def clarify(self, run: TripRun, message: str) -> TripRun:
        """Fill missing intent fields from a clarification reply (same TripRun).

        Only missing fields are filled, unless the message signals a correction.
        Memory enrichment + required-field validation are re-run, updating
        requires_clarification / clarification_question. The phase is unchanged
        (the caller advances afterwards).
        """
        if run.phase in TERMINAL_PHASES:
            raise CannotAdvance("Trip is already finalized; start a new trip")

        intent = run.intent or TripIntent()
        correction = _is_correction(message)
        parsed = self._interpret_clarification(run, message)

        def _origin_incomplete() -> bool:
            return intent.origin is None or intent.origin.airport is None

        def _destination_incomplete() -> bool:
            return intent.destination is None or intent.destination.airport is None

        if parsed["origin"] is not None and (correction or _origin_incomplete()):
            intent.origin = parsed["origin"]
        if parsed["destination"] is not None and (correction or _destination_incomplete()):
            intent.destination = parsed["destination"]
        if parsed["start_date"] is not None and (correction or intent.start_date is None):
            intent.start_date = parsed["start_date"]
        if parsed["end_date"] is not None and (correction or intent.end_date is None):
            intent.end_date = parsed["end_date"]

        # Re-run memory enrichment (fills origin from home if still missing),
        # then airport resolution + required-field validation via the agent.
        items = self.memory_agent.retrieve()
        intent = self.memory_agent.enrich(intent, items).intent
        result = self.location_understanding_agent.understand(run.request_text, intent)
        run.intent = result.intent
        run.requires_clarification = result.requires_clarification
        run.clarification_question = result.clarification_question

        output = {
            "message": message,
            "intent": run.intent.model_dump(mode="json"),
            "requires_clarification": run.requires_clarification,
            "clarification_question": run.clarification_question,
            "resolver_notes": result.notes,
        }
        self._record_step(run, "clarify", message, output)
        return run

    def _interpret_clarification(self, run: TripRun, message: str) -> dict:
        """Read a clarification reply into {origin, destination, start_date, end_date}.

        Uses the LLM when enabled — it is the only path that understands bare
        answers ("GRU", "Recife", "10 a 15 de setembro"), because it receives the
        pending question as context. Falls back to the deterministic parser when
        the LLM is off, fails, or extracts nothing.
        """
        settings = get_settings()
        deterministic = parse_clarification(message, settings.default_trip_year)
        if not settings.llm_enabled:
            return deterministic
        try:
            extraction = self._intent_agent().interpret_clarification(
                message,
                question=run.clarification_question,
                intent_summary=_intent_summary(run.intent),
            )
        except Exception as exc:  # any LLM/parse failure → deterministic
            logger.warning("Gemini clarification parse failed; using regex parser: %s", exc)
            return deterministic
        parsed = {
            "origin": location_from_answer(extraction.origin_text),
            "destination": location_from_answer(extraction.destination_text),
            "start_date": extraction.start_date,
            "end_date": extraction.end_date,
        }
        # The model may legitimately extract nothing (off-topic reply) — keep
        # whatever the regex parser found rather than losing it.
        return parsed if any(parsed.values()) else deterministic

    def _intent_agent(self):
        """The IntentUnderstandingAgent used for LLM-backed clarification."""
        # Lazy import keeps the orchestrator import graph free of agent cycles.
        from app.agents.intent_understanding_agent import IntentUnderstandingAgent

        if self._intent_understanding_agent is None:
            self._intent_understanding_agent = IntentUnderstandingAgent()
        return self._intent_understanding_agent

    @staticmethod
    def _stop_reason(run: TripRun) -> str | None:
        """Return the stop reason if the run should halt, else None."""
        if run.requires_clarification:
            return "clarification_required"
        if run.policy_result is not None and run.policy_result.status == "block":
            return "policy_block"
        approval = run.approval_result
        if approval is not None:
            if approval.status is ApprovalStatus.REJECTED:
                return "rejected"
            if approval.status is ApprovalStatus.PENDING:
                return "awaiting_approval"
        if run.phase is TripPhase.COMPLETED:
            return "completed"
        if run.phase is TripPhase.REJECTED:
            return "rejected"
        return None

    # --- human-in-the-loop approval -------------------------------------

    def approve(self, run: TripRun, reviewer: str, comments: str | None = None) -> TripRun:
        """Record an approval decision (run must be pending at the gate)."""
        return self._decide(run, "approved", reviewer, comments)

    def reject(self, run: TripRun, reviewer: str, comments: str | None = None) -> TripRun:
        """Record a rejection decision (run must be pending at the gate)."""
        return self._decide(run, "rejected", reviewer, comments)

    def _decide(self, run: TripRun, decision: str, reviewer: str, comments: str | None) -> TripRun:
        if (
            run.phase is not TripPhase.AWAITING_APPROVAL
            or run.approval_result is None
            or run.approval_result.status is not ApprovalStatus.PENDING
        ):
            raise CannotAdvance("Trip is not awaiting approval")
        status = ApprovalStatus.APPROVED if decision == "approved" else ApprovalStatus.REJECTED
        run.approval_result.status = status
        # A rejection is final: move to the terminal phase now. (An approval only
        # unlocks the gate — the report is still produced by advance().)
        if status is ApprovalStatus.REJECTED:
            run.phase = TripPhase.REJECTED
        run.approval_result.decision = ApprovalDecision(
            decision=decision,
            reviewer=reviewer,
            comments=comments,
            timestamp=datetime.now(timezone.utc),
        )
        self._record_step(
            run, "approval_decision", reviewer,
            run.approval_result.model_dump(mode="json"),
        )
        return run

    def _approval_gate_next(self, run: TripRun) -> TripPhase:
        """Decide the successor of AWAITING_APPROVAL from the approval status."""
        status = (
            run.approval_result.status
            if run.approval_result is not None
            else ApprovalStatus.PENDING
        )
        if status is ApprovalStatus.APPROVED:
            return TripPhase.GENERATING_REPORT
        if status is ApprovalStatus.REJECTED:
            raise CannotAdvance("Trip was rejected by the reviewer; cannot proceed")
        raise CannotAdvance("Trip is awaiting human approval")

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _record_step(run: TripRun, name: str, input_obj, output_obj) -> None:
        """Append a recorded Step (JSON-friendly input/output) to the run."""
        run.steps.append(
            Step(
                name=name,
                status="done",
                order=len(run.steps) + 1,
                input=_jsonify(input_obj),
                output=_jsonify(output_obj),
            )
        )


def _jsonify(value):
    """Best-effort conversion of a Pydantic model to a JSON-friendly value."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value
