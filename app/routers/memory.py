"""Memory inspection endpoint. See specs/api.md (GET /memory)."""

from __future__ import annotations

from fastapi import APIRouter

from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import MemoryItem, MemoryReadResult

router = APIRouter(prefix="/memory", tags=["memory"])

# Skeleton-stage singleton seeded with traveler preferences.
# TODO: share a single SQLite-backed MemoryRepository via dependency injection.
_memory = MemoryRepository()


@router.get("", response_model=MemoryReadResult)
def get_memory() -> MemoryReadResult:
    """Return all memory items (seed + learned)."""
    items: list[MemoryItem] = _memory.all()
    return MemoryReadResult(items=items)
