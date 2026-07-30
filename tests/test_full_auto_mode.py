"""End-to-end Full Auto Mode tests.

Auto-run advances UNDERSTANDING → ... → POLICY automatically and, for PASS/WARN,
stops only at APPROVAL. After approval, a second auto-run continues to the REPORT
and COMPLETED. Step history is preserved throughout.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.orchestrator.orchestrator import Orchestrator
from app.repositories.trip_repository import TripRepository
from app.schemas.trip import TripPhase, TripRun

_PASS_REQUEST = (
    "Preciso planejar uma viagem corporativa de Curitiba para Belo Horizonte "
    "entre 08 e 13 de junho para reuniões do EnergyGPT."
)
_WARN_REQUEST = (  # long stay pushes total into the 8000–10000 warn band
    "Preciso planejar uma viagem corporativa de Curitiba para Belo Horizonte "
    "entre 01 e 16 de junho para reuniões do EnergyGPT."
)
_BLOCK_REQUEST = (  # 30-day stay pushes total over the 10000 hard limit
    "Preciso planejar uma viagem corporativa de Curitiba para Belo Horizonte "
    "entre 01 e 30 de junho para reuniões do EnergyGPT."
)

_EXPECTED_STEPS_TO_APPROVAL = [
    "understand_request", "create_plan", "retrieve_memory", "resolve_locations",
    "search_flights", "search_hotels", "rank_flights", "rank_hotels",
    "recommend_trip", "estimate_budget", "validate_policy", "wait_for_approval",
]


def _auto(repo: TripRepository, orch: Orchestrator, request_text: str) -> TripRun:
    run = TripRun(id=str(uuid4()), request_text=request_text,
                  phase=TripPhase.CREATED, created_at=datetime.now(timezone.utc))
    repo.add(run)
    orch.run_until_stop(run)
    repo.save(run)
    return run


def test_auto_runs_to_approval_for_pass():
    repo, orch = TripRepository(), Orchestrator(trip_repository=TripRepository())
    orch.trip_repository = repo
    run = _auto(repo, orch, _PASS_REQUEST)

    assert run.phase is TripPhase.AWAITING_APPROVAL
    assert run.policy_result.status == "pass"
    assert run.approval_result.status.value == "pending"
    # Full pipeline ran automatically, step history preserved & ordered.
    assert [s.name for s in run.steps] == _EXPECTED_STEPS_TO_APPROVAL


def test_auto_continues_to_report_after_approval():
    repo, orch = TripRepository(), Orchestrator()
    orch.trip_repository = repo
    run = _auto(repo, orch, _PASS_REQUEST)

    # Human approves, then a second auto-run continues to the REPORT/COMPLETED.
    orch.approve(run, reviewer="maria.gestora", comments="ok")
    summary = orch.run_until_stop(run)
    repo.save(run)

    assert summary.stop_reason == "completed"
    assert run.phase is TripPhase.COMPLETED
    assert run.report is not None
    assert run.report.title == "Relatório de Viagem Corporativa"
    # Earlier steps preserved; report step appended.
    names = [s.name for s in run.steps]
    assert names[: len(_EXPECTED_STEPS_TO_APPROVAL)] == _EXPECTED_STEPS_TO_APPROVAL
    assert names[-2:] == ["approval_decision", "generate_report"]


def test_warn_also_stops_only_at_approval():
    repo, orch = TripRepository(), Orchestrator()
    orch.trip_repository = repo
    run = _auto(repo, orch, _WARN_REQUEST)

    assert run.policy_result.status == "warn"
    assert run.phase is TripPhase.AWAITING_APPROVAL  # warn still reaches approval
    assert run.approval_result.status.value == "pending"


def test_block_never_reaches_approval():
    repo, orch = TripRepository(), Orchestrator()
    orch.trip_repository = repo
    run = _auto(repo, orch, _BLOCK_REQUEST)

    assert run.policy_result.status == "block"
    assert run.phase is TripPhase.VALIDATING_POLICY
    assert run.approval_result is None  # never opened approval


def test_observability_preserved_step_outputs():
    repo, orch = TripRepository(), Orchestrator()
    orch.trip_repository = repo
    run = _auto(repo, orch, _PASS_REQUEST)
    by_name = {s.name: s for s in run.steps}
    # Each recorded step keeps its input/output for observability.
    assert by_name["search_flights"].output["tool_calls"]
    assert by_name["validate_policy"].output["policy_result"]["status"] == "pass"
    assert by_name["estimate_budget"].output["budget_estimate"]["total"] > 0
