"""TripRepository — stores TripRuns.

SQLite-ready: the interface mirrors what a real `runs`/`steps` table will back.
For the skeleton, runs are held in an in-memory dict.
"""

from __future__ import annotations

from typing import Optional

from app.schemas.trip import TripRun


class TripRepository:
    """In-memory store of trip runs (to be backed by SQLite later)."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        # TODO: open a SQLite connection from database_url and ensure schema.
        self.database_url = database_url
        self._runs: dict[str, TripRun] = {}

    def add(self, run: TripRun) -> TripRun:
        # TODO: INSERT into the runs table.
        self._runs[run.id] = run
        return run

    def get(self, trip_id: str) -> Optional[TripRun]:
        # TODO: SELECT by id.
        return self._runs.get(trip_id)

    def list(self) -> list[TripRun]:
        # TODO: SELECT all.
        return list(self._runs.values())

    def save(self, run: TripRun) -> TripRun:
        # TODO: UPDATE the run row (phase, steps, attached results).
        self._runs[run.id] = run
        return run
