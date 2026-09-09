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
from atdd.coach.gate.phase_edges import declared_autonomy

logger = logging.getLogger(__name__)

GATE_ID = "approval-token"
RULE_ID = "govern-lifecycle.E050.operator-approval-required"


# The three strings every verdict below is phrased in terms of. Derived from ctx
# rather than threaded through as parameters: each regime's method needs a
# different subset, and passing all three to each was what pushed `run` past the
# `coder.refactor.complexity-length` threshold in the first place.
def _rel(ctx: GateContext):
    """The token's path RELATIVE to the Control Root — what an operator reads."""
    return approval_relpath(ctx.issue_number, ctx.from_phase, ctx.to_phase)


def _edge(ctx: GateContext) -> str:
    """``FROM->TO``, upper-cased, as the token's own scope spells it."""
    return f"{ctx.from_phase.upper()}->{ctx.to_phase.upper()}"


def _produce(ctx: GateContext) -> str:
    """The remedy every refusal ends with — what to run to get a valid token."""
    return (
        f"operator must approve: atdd coach approve {ctx.issue_number} "
        f"--transition {_edge(ctx)}"
    )


#: The one autonomy value that lifts the operator token. Matched EXACTLY: the
#: vocabulary is closed and validated by D020 (#1626), so a near-miss is a
#: malformed declaration, and a gate must not open on one.
_AGENT = "agent"


def _declared_autonomy(from_phase: str) -> Optional[str]:
    """The submitting authority the machine declares for ``from_phase``.

    A seam, so the fail-closed policy above can be exercised without writing a
    malformed phase machine to disk.
    """
    return declared_autonomy(from_phase)


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

    def _autonomy_waiver(self, ctx: GateContext) -> Optional[GateCheckResult]:
        """NOT_APPLICABLE when the machine hands this edge to the persona (#1798).

        `gate.transitions` gates an EDGE, and two checks of different kinds ride
        on SMOKE->REFACTOR: the #1602 evidence check the edge was listed to
        enable, and this one, which attached as collateral. The machine already
        declares who may submit, so read it rather than demanding a human where
        the convention does not.

        Fail-closed: ONLY an exact `agent` waives the token. An unreadable
        machine is reported and treated as unknown — the moment the convention
        cannot be read is the moment to keep the gate shut, the same reasoning
        `phase_edges` uses to refuse a fallback phase list.
        """
        try:
            autonomy = _declared_autonomy(ctx.from_phase)
        except Exception as exc:  # noqa: BLE001 - reported below, never swallowed
            logger.warning(
                "declared autonomy unreadable; keeping the approval gate",
                extra={"gate_id": self.gate_id, "rule_id": self.rule_id,
                       "issue": ctx.issue_number, "edge": _edge(ctx),
                       "from_phase": ctx.from_phase, "error": str(exc)},
            )
            return None

        if autonomy != _AGENT:
            return None

        return GateCheckResult.not_applicable(
            self.gate_id, self.rule_id,
            f"{_edge(ctx)} declares `autonomy: {_AGENT}`, so no operator "
            f"approval token is owed; the persona may submit it",
        )

    def run(self, ctx: GateContext) -> GateCheckResult:
        waiver = self._autonomy_waiver(ctx)
        if waiver is not None:
            return waiver

        # #1376: the base is the SHARED Control Root (#1346), not ctx.worktree —
        # which _transition_gate sets to the literal cwd. Resolving here what
        # `atdd coach approve` resolves at mint is what makes the token a receipt
        # rather than a file whose visibility depends on which worktree is current.
        # A worktree-local token from before this change is still honored.
        location = locate_approval_token(
            ctx.worktree, ctx.issue_number, ctx.from_phase, ctx.to_phase
        )
        key = self.signing_key if self.signing_key is not None else resolve_signing_key()

        if not location.exists:
            return GateCheckResult(
                self.gate_id, self.rule_id, False,
                f"no operator approval token for {_edge(ctx)} (expected {_rel(ctx)} "
                f"under the Control Root: {location.control_root_path}); "
                f"{_produce(ctx)}",
            )
        if location.legacy:
            logger.warning(
                "approval token read from the worktree-local back-compat path (#1376)",
                extra={"gate_id": self.gate_id, "rule_id": self.rule_id,
                       "issue": ctx.issue_number, "path": str(location.worktree_path),
                       "control_root_path": str(location.control_root_path)},
            )
        try:
            token_data = json.loads(location.path.read_text())
        except (OSError, ValueError) as exc:
            logger.warning(
                "approval token unreadable; failing closed",
                extra={"gate_id": self.gate_id, "rule_id": self.rule_id,
                       "path": str(location.path), "issue": ctx.issue_number,
                       "error": str(exc)},
            )
            return GateCheckResult(
                self.gate_id, self.rule_id, False,
                f"approval token at {_rel(ctx)} is unreadable/unparseable "
                f"(fail-closed): {exc}; {_produce(ctx)}",
            )

        # WHICH REGIME the token belongs to is read off the token itself, never off
        # a date or a migration flag, so the answer needs no state and cannot drift.
        if not token_data.get("branch") and not token_data.get("expires_at"):
            return self._pre_binding_verdict(token_data, ctx, key)
        return self._bound_verdict(token_data, ctx, key)

    # -- the two regimes, one method each ----------------------------------- #
    def _pre_binding_verdict(self, token_data, ctx: GateContext, key) -> GateCheckResult:
        """A token carrying NEITHER a branch nor an expiry: verified as it always was.

        169 such tokens were measured on 2026-08-03 — the entire corpus at the time
        — because the mint never passed either field. They are verified with no
        branch and no clock, which is the pre-#1525 contract ``verify_token``
        preserves by defaulting both to ``None``.

        The same boundary #1718 drew for ``schema_version``: a token is read under
        the regime it was minted in, never retro-invalidated by a rule that did not
        exist when it was signed. Drawn on what the token CARRIES rather than on
        when it was found, so it needs no migration and no cutoff date.

        And the pass message SAYS so. A regime nobody surfaces is a regime nobody
        reads, so an unbound token cannot quietly present here as a bound one.
        """
        if verify_token(token_data, ctx.issue_number, ctx.from_phase, ctx.to_phase, key):
            return GateCheckResult(
                self.gate_id, self.rule_id, True,
                f"approval token present for {_edge(ctx)} (PRE-BINDING token: bound "
                f"to no branch and carrying no expiry, so it is accepted under the "
                f"regime it was minted in): {describe_attribution(token_data)}",
            )
        return GateCheckResult(
            self.gate_id, self.rule_id, False,
            f"approval token at {_rel(ctx)} does not match this transition or its "
            f"signature is invalid (scope/signature mismatch); {_produce(ctx)}",
        )

    def _bound_verdict(self, token_data, ctx: GateContext, key) -> GateCheckResult:
        """A token asserting a branch and/or an expiry: both are ENFORCED here.

        This is the half #1525 built and no call site ever reached. The branch comes
        from the State Store's issue binding — see ``approval_binding`` for why it
        must not come from the cwd — and the clock from ``self.now`` or the wall.
        """
        binding = resolve_issue_branch(ctx.worktree, ctx.issue_number)
        if not binding:
            # COULD_NOT_CHECK, not FAIL (#1719/C013). The token asserts a branch
            # binding and the check ran to completion without being able to observe
            # what that binding currently is. "I could not look" is a different
            # fact from "the rule is violated", and the operator's next action is
            # different too — which is the whole reason this verdict exists.
            return GateCheckResult.could_not_check(
                self.gate_id, self.rule_id,
                f"approval token at {_rel(ctx)} is bound to a branch, but the branch "
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
                f"approval token present for {_edge(ctx)} (bound to branch "
                f"{binding.branch}, valid until {token_data.get('expires_at')}): "
                f"{describe_attribution(token_data)}",
            )
        return GateCheckResult(
            self.gate_id, self.rule_id, False,
            f"approval token at {_rel(ctx)} "
            f"{self._diagnose(token_data, ctx, key, binding.branch, now)}; "
            f"{_produce(ctx)}",
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
