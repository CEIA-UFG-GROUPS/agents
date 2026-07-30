"""policy_tool — evaluate corporate travel policy rules. See specs/tools.md.

Rules (illustrative, thresholds in app/core/policy_config.py):
  R1 — Trip purpose is required.                 missing -> block,  else pass
  R2 — Total budget limit (8000 / 10000 BRL).    <=8000 pass, <=10000 warn, else block
  R3 — Hotel nightly rate <= 500 BRL/night.      over -> warn, else pass
  R4 — Prefer direct flights.                    0 stops pass, else warn
  R5 — Corporate trips always need human approval (severity info, always).

Status aggregation: any block -> block; else any warn -> warn; else pass.
"""

from __future__ import annotations

from app.core.policy_config import (
    HOTEL_NIGHTLY_LIMIT,
    TRIP_BUDGET_BLOCK,
    TRIP_BUDGET_LIMIT,
)
from app.schemas.policy import Finding, PolicyInput, PolicyResult


class PolicyTool:
    """Validate a proposed trip against policy rules."""

    name = "policy_tool"

    def evaluate(self, payload: PolicyInput) -> PolicyResult:
        findings: list[Finding] = []

        # R1 — Trip purpose required.
        purpose = getattr(payload.intent, "purpose", None)
        if purpose:
            findings.append(Finding(rule_id="R1", severity="pass", message="Trip purpose is present."))
        else:
            findings.append(Finding(rule_id="R1", severity="block", message="Trip purpose is missing."))

        # R2 — Total budget limit.
        total = getattr(payload.budget, "total", None)
        if total is not None:
            if total <= TRIP_BUDGET_LIMIT:
                findings.append(Finding(
                    rule_id="R2", severity="pass",
                    message=f"Total budget {total:.2f} BRL is within the {TRIP_BUDGET_LIMIT} BRL limit.",
                ))
            elif total <= TRIP_BUDGET_BLOCK:
                findings.append(Finding(
                    rule_id="R2", severity="warn",
                    message=f"Total budget {total:.2f} BRL exceeds {TRIP_BUDGET_LIMIT} BRL "
                            f"(within {TRIP_BUDGET_BLOCK} BRL tolerance).",
                ))
            else:
                findings.append(Finding(
                    rule_id="R2", severity="block",
                    message=f"Total budget {total:.2f} BRL exceeds the {TRIP_BUDGET_BLOCK} BRL hard limit.",
                ))

        # R3 — Hotel nightly rate.
        nightly_rate = getattr(payload.hotel, "nightly_rate", None)
        if nightly_rate is not None:
            if nightly_rate <= HOTEL_NIGHTLY_LIMIT:
                findings.append(Finding(
                    rule_id="R3", severity="pass",
                    message=f"Hotel nightly rate {nightly_rate:.2f} BRL is within the {HOTEL_NIGHTLY_LIMIT} BRL limit.",
                ))
            else:
                findings.append(Finding(
                    rule_id="R3", severity="warn",
                    message=f"Hotel nightly rate {nightly_rate:.2f} BRL exceeds the {HOTEL_NIGHTLY_LIMIT} BRL limit.",
                ))

        # R4 — Prefer direct flights.
        stops = getattr(payload.flight, "stops", None)
        if stops is not None:
            if stops == 0:
                findings.append(Finding(rule_id="R4", severity="pass", message="Selected flight is non-stop."))
            else:
                findings.append(Finding(
                    rule_id="R4", severity="warn",
                    message=f"Selected flight has {stops} stop(s); direct flights are preferred.",
                ))

        # R5 — Human approval always required.
        findings.append(Finding(
            rule_id="R5", severity="info",
            message="Corporate trips always require human approval.",
        ))

        return PolicyResult(
            status=self._aggregate(findings),
            findings=findings,
            requires_human_approval=True,
        )

    @staticmethod
    def _aggregate(findings: list[Finding]) -> str:
        """block if any block; else warn if any warn; else pass."""
        severities = {f.severity for f in findings}
        if "block" in severities:
            return "block"
        if "warn" in severities:
            return "warn"
        return "pass"
