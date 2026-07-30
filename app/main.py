"""FastAPI application entry point.

Run with:  uv run uvicorn app.main:app --reload
Swagger UI: http://127.0.0.1:8000/docs

This is the skeleton stage: endpoints and structure exist; full business logic
is pending (see TODO comments throughout the package and specs/ for the design).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.dev_seed import diagnostics_banner, new_seeded_run
from app.llm.gemini_client import llm_status
from app.orchestrator.orchestrator import CannotAdvance
from app.routers import memory, tools, trips

settings = get_settings()


def _run_seeded_pipeline() -> None:
    """Create a seeded run and advance it through every implemented phase.

    Uses the trips router's shared repository/orchestrator so the result is
    queryable via GET /trips. Stops cleanly when it reaches a phase that is not
    implemented yet (or the approval gate).
    """
    run = new_seeded_run()
    trips._trips.add(run)
    while True:
        try:
            trips._orchestrator.advance(run)
        except (CannotAdvance, NotImplementedError):
            break
        trips._trips.save(run)
    print(f"[dev] Seeded trip {run.id} executed to phase {run.phase.value}", flush=True)


def _print_llm_diagnostics() -> None:
    """Print safe LLM config at startup (never the API key)."""
    status = llm_status(settings)
    print(f"LLM enabled: {str(status['llm_enabled']).lower()}", flush=True)
    print(f"Gemini model: {status['model']}", flush=True)
    print(f"Gemini API key configured: {str(status['api_key_configured']).lower()}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _print_llm_diagnostics()
    if settings.dev_mode:
        print(diagnostics_banner(), flush=True)
        _run_seeded_pipeline()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Educational corporate-travel multi-agent demo. "
        "See the specs/ directory for the full specification."
    ),
    lifespan=lifespan,
)

app.include_router(trips.router)
app.include_router(memory.router)
app.include_router(tools.router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}
