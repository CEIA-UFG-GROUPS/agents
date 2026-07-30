"""Shared agent contract.

Every agent implements `run(context) -> result`. `context` is a loose dict-like
carrier for the skeleton; it will become a typed RunContext once the
orchestrator is implemented.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

RunContext = dict[str, Any]


class Agent(ABC):
    """Base class for all worker agents."""

    name: str = "agent"

    @abstractmethod
    def run(self, context: RunContext) -> Any:
        """Do this agent's one job and return a typed result."""
        raise NotImplementedError
