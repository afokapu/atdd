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

WHAT the token must be bound to is ``approval_binding`` (#1721): the branch the
State Store binds the issue to, and the moment the approval stops being valid.
#1525 built both into ``verify_token`` and this consumer passed NEITHER, so the
binding was inert — a token minted for one branch satisfied the gate on any
other, and an approval signed weeks ago satisfied it today. Both arguments are
passed now, so the property is enforced HERE and not merely recorded.

AND THE REFUSAL SAYS WHICH (#1721). ``verify_token`` answers with a bool, so an
expired token and a forged one used to produce the same sentence — "does not
match this transition or its signature is invalid". That is the defect this
program is named for in miniature: a gate that refuses without naming its cause
leaves the operator to guess between re-approving, fixing a branch binding, and
suspecting tampering. :meth:`ApprovalTokenGateCheck._diagnose` recovers the cause
by re-running the SAME pure verifier with narrowed inputs — no signing logic is
duplicated or reimplemented here, and #1525's module is untouched.

FAIL-CLOSED (the #1020 E046 rule): an absent token file, an unparseable token,
a mis-scoped token, or a forged signature is a FAIL with a clear operator
message — never a silent pass. A token that IS bound but whose branch binding
cannot be observed is a COULD_NOT_CHECK (#1719/C013), not a FAIL: the check ran
to completion and could not perform its observation, and the operator's next
action differs completely from the one a violation calls for. Feed-decoupled: it
reads the filesystem, so the cmux ~120s soft-expiry cannot satisfy or bypass it
(#1017).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from atdd.coach.gate.approval import (
    approval_relpath,
    describe_attribution,
    resolve_signing_key,
    verify_token,
)
from atdd.coach.gate.approval_binding import resolve_issue_branch
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
    # None => read the wall clock at run time. Pinned by a caller that needs the
    # expiry verdict to be deterministic, mirroring ``signing_key`` rather than
    # inventing a second injection style. ISO-8601, as ``verify_token`` takes it.
    now: Optional[str] = None

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

        edge = f"{ctx.from_phase.upper()}->{ctx.to_phase.upper()}"
        token_branch = token_data.get("branch")
        token_expiry = token_data.get("expires_at")

        # THE EARLIER REGIME (#1721). A token carrying neither field predates the
        # binding — 169 such tokens were measured on 2026-08-03 — and is verified
        # exactly as it was before, with no branch and no clock. This is the same
        # boundary #1718 drew for `schema_version`: a token is read under the
        # regime it was minted in, never retro-invalidated by a rule that did not
        # exist when it was signed. The pass message SAYS which regime it is, so
        # an unbound token cannot quietly present as a bound one.
        if not token_branch and not token_expiry:
            if verify_token(token_data, ctx.issue_number, ctx.from_phase, ctx.to_phase, key):
                return GateCheckResult(
                    self.gate_id, self.rule_id, True,
                    f"approval token present for {edge} (PRE-BINDING token: bound to "
                    f"no branch and carrying no expiry, so it is accepted under the "
                    f"regime it was minted in): {describe_attribution(token_data)}",
                )
            return GateCheckResult(
                self.gate_id, self.rule_id, False,
                f"approval token at {rel} does not match this transition or its "
                f"signature is invalid (scope/signature mismatch); {produce}",
            )

        binding = resolve_issue_branch(ctx.worktree, ctx.issue_number)
        if not binding:
            # COULD_NOT_CHECK, not FAIL (#1719/C013). The token asserts a branch
            # binding and the check ran to completion without being able to observe
            # what that binding currently is. "I could not look" is a different
            # fact from "the rule is violated", and the operator's next action is
            # different too — which is the whole reason this verdict exists.
            return GateCheckResult.could_not_check(
                self.gate_id, self.rule_id,
                f"approval token at {rel} is bound to a branch, but the branch "
                f"#{ctx.issue_number} is bound to could not be observed, so the "
                f"binding could not be checked: {binding.reason}",
            )

        now = self.now if self.now is not None else datetime.now(timezone.utc).isoformat()
        if verify_token(
            token_data, ctx.issue_number, ctx.from_phase, ctx.to_phase, key,
            branch=binding.branch, now=now,
        ):
            # Report WHAT the token says produced it, not merely that one exists
            # (#1718). A version stamp nobody surfaces is a stamp nobody reads, and
            # the point of versioning was to stop a pre-attribution token from
            # passing as an operator approval on the strength of its approved_by.
            return GateCheckResult(
                self.gate_id, self.rule_id, True,
                f"approval token present for {edge} (bound to branch "
                f"{binding.branch}, valid until {token_expiry}): "
                f"{describe_attribution(token_data)}",
            )
        return GateCheckResult(
            self.gate_id, self.rule_id, False,
            f"approval token at {rel} "
            f"{self._diagnose(token_data, ctx, key, binding.branch, now)}; {produce}",
        )

    def _diagnose(self, token_data, ctx: GateContext, key, branch: str, now: str) -> str:
        """WHY a bound token failed, recovered by re-asking the same pure verifier.

        ``verify_token`` returns a bool, so the cause has to be reconstructed from
        outside it — by narrowing one input at a time and seeing which narrowing
        makes the answer flip. Nothing here reimplements signing: every branch below
        is a call to the same #1525 function the verdict above used, which is what
        keeps the diagnosis honest. If it ever disagreed with the verdict, the
        verdict wins — the fallback clause says the least and blocks the same.

        The order matters. Expiry is asked FIRST because it is the only cause that
        leaves the signature intact, so it is the only one that can be established
        by elimination rather than guessed at.
        """
        args = (token_data, ctx.issue_number, ctx.from_phase, ctx.to_phase, key)

        # Signature and scope are fine on this branch; only the clock refused.
        if verify_token(*args, branch=branch):
            return (
                f"EXPIRED: it was valid until {token_data.get('expires_at')!r} and it "
                f"is now {now}. An approval is granted for a bounded time (#1721); "
                f"re-approve to get a fresh one"
            )

        token_branch = token_data.get("branch")
        if not token_branch:
            return (
                f"carries an expiry but NO BRANCH BINDING, while #{ctx.issue_number} "
                f"is bound to branch {branch!r}. A branchless token cannot satisfy a "
                f"branch-scoped check; re-approve to mint a bound one"
            )
        if verify_token(*args, branch=token_branch):
            return (
                f"was minted while #{ctx.issue_number} was bound to branch "
                f"{token_branch!r}, and #{ctx.issue_number} is now bound to "
                f"{branch!r} — THE BRANCH CHANGED under the approval. The token is "
                f"intact and no longer applies to this work; re-approve on the "
                f"current branch"
            )
        return (
            f"does not match this transition or its signature is invalid "
            f"(scope/signature mismatch)"
        )
