"""memory_tool — read/write the SQLite-backed memory store. See specs/tools.md.

Delegates to MemoryRepository so storage details stay in the repository layer.
"""

from __future__ import annotations

from app.schemas.memory import (
    MemoryQuery,
    MemoryReadResult,
    MemoryWrite,
    MemoryWriteResult,
)


class MemoryTool:
    """Thin tool wrapper over the memory repository."""

    name = "memory_tool"

    def __init__(self, repository=None) -> None:
        # TODO: inject a MemoryRepository instance.
        self.repository = repository

    def read(self, query: MemoryQuery) -> MemoryReadResult:
        # TODO: delegate to repository.query(...)
        return MemoryReadResult(items=[])

    def write(self, item: MemoryWrite) -> MemoryWriteResult:
        # TODO: delegate to repository.add(...)
        return MemoryWriteResult(stored=False)
