"""Human-in-the-loop approval schemas.

A run that passes (or warns on) policy enters AWAITING_APPROVAL with a pending
ApprovalResult. A reviewer then approves or rejects it. See specs/agents.md
(HumanApproval).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel


class ApprovalStatus(str, Enum):
    """Lifecycle of a human approval decision."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalDecision(BaseModel):
    """The reviewer's recorded decision."""

    decision: Literal["approved", "rejected"]
    reviewer: str
    comments: Optional[str] = None
    timestamp: datetime


class ApprovalResult(BaseModel):
    """Approval state attached to a TripRun."""

    status: ApprovalStatus = ApprovalStatus.PENDING
    requires_human_approval: bool = True
    decision: Optional[ApprovalDecision] = None


class ApprovalRequest(BaseModel):
    """Inbound body for the approve/reject endpoints."""

    reviewer: str
    comments: Optional[str] = None
