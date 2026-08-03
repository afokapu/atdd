"""ApprovalTokenGateCheck — the operator-approval check registered INTO #1020.

The filesystem-reading sibling of the pure ``approval`` module: it loads the
token and delegates the verdict to ``verify_token``. It satisfies the #1020
``GateCheck`` Protocol (``gate_id`` / ``rule_id`` / ``run``), so #1017 registers
it INTO ``GATE_REGISTRY`` rather than forking ``IssueLifecycle.transition`` logic.

WHERE it loads the token from is ``approval_paths`` (#1376): the single shared
Control Root, the same base ``atdd coach approve`` mints against. Before #1376
this joined ``approval_relpath`` onto ``ctx.worktree`` — the literal cwd
``IssueLifecycle._transition_gate`` hands over — so a token minted from one
worktree was invisible to a gate evaluating from a sibling. A worktree-local
token from before the change is still read, as a back-compat fallback.

FAIL-CLOSED (the #1020 E046 rule): an absent token file, an unparseable token,
a mis-scoped token, or a forged signature is a FAIL with a clear operator
message — never a silent pass. Feed-decoupled: it reads the filesystem, so the
cmux ~120s soft-expiry cannot satisfy or bypass it (#1017).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from atdd.coach.gate.approval import (
    approval_relpath,
    describe_attribution,
    resolve_signing_key,
    verify_token,
)
from atdd.coach.gate.approval_paths import locate_approval_token
from atdd.coach.gate.decision import GateCheckResult, GateContext

logger = logging.getLogger(__name__)

GATE_ID = "approval-token"
RULE_ID = "govern-lifecycle.E050.operator-approval-required"


@dataclass(frozen=True)
class ApprovalTokenGateCheck:
    """Passes iff an operator-signed approval token exists for the transition."""

    gate_id: str = GATE_ID
    rule_id: str = RULE_ID
    # None => resolve the signing key from the environment at run time. A test or
    # caller may pin an explicit key for determinism.
    signing_key: Optional[str] = None

    def run(self, ctx: GateContext) -> GateCheckResult:
        rel = approval_relpath(ctx.issue_number, ctx.from_phase, ctx.to_phase)
        # #1376: the base is the SHARED Control Root (#1346), not ctx.worktree —
        # which _transition_gate sets to the literal cwd. Resolving here what
        # `atdd coach approve` resolves at mint is what makes the token a receipt
        # rather than a file whose visibility depends on which worktree is current.
        # A worktree-local token from before this change is still honored.
        location = locate_approval_token(
            ctx.worktree, ctx.issue_number, ctx.from_phase, ctx.to_phase
        )
        token_path = location.path
        key = self.signing_key if self.signing_key is not None else resolve_signing_key()
        produce = (
            f"operator must approve: atdd coach approve {ctx.issue_number} "
            f"--transition {ctx.from_phase.upper()}->{ctx.to_phase.upper()}"
        )

        if not location.exists:
            return GateCheckResult(
                self.gate_id, self.rule_id, False,
                f"no operator approval token for "
                f"{ctx.from_phase.upper()}->{ctx.to_phase.upper()} (expected {rel} "
                f"under the Control Root: {location.control_root_path}); {produce}",
            )
        if location.legacy:
            logger.warning(
                "approval token read from the worktree-local back-compat path (#1376)",
                extra={"gate_id": self.gate_id, "rule_id": self.rule_id,
                       "issue": ctx.issue_number, "path": str(location.worktree_path),
                       "control_root_path": str(location.control_root_path)},
            )
        try:
            token_data = json.loads(token_path.read_text())
        except (OSError, ValueError) as exc:
            logger.warning(
                "approval token unreadable; failing closed",
                extra={"gate_id": self.gate_id, "rule_id": self.rule_id,
                       "path": str(token_path), "issue": ctx.issue_number, "error": str(exc)},
            )
            return GateCheckResult(
                self.gate_id, self.rule_id, False,
                f"approval token at {rel} is unreadable/unparseable (fail-closed): {exc}; {produce}",
            )

        if verify_token(token_data, ctx.issue_number, ctx.from_phase, ctx.to_phase, key):
            # Report WHAT the token says produced it, not merely that one exists
            # (#1718). A version stamp nobody surfaces is a stamp nobody reads, and
            # the point of versioning was to stop a pre-attribution token from
            # passing as an operator approval on the strength of its approved_by.
            return GateCheckResult(
                self.gate_id, self.rule_id, True,
                f"approval token present for "
                f"{ctx.from_phase.upper()}->{ctx.to_phase.upper()}: "
                f"{describe_attribution(token_data)}",
            )
        return GateCheckResult(
            self.gate_id, self.rule_id, False,
            f"approval token at {rel} does not match this transition or its signature "
            f"is invalid (scope/signature mismatch); {produce}",
        )
