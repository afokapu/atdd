"""What the approval token is bound TO — resolved identically at mint and at check.

``approval_paths`` (#1376) owns WHERE the token lives and made that answer the same
at both ends. This module owns the other two components #1525 built into the signed
scope and neither call site ever passed: the BRANCH the approval is for, and the
MOMENT it stops being valid. It exists for the same reason its sibling does — the
mint and the gate run in two processes, potentially from two different worktrees,
and a binding they resolve differently is a binding that means nothing.

THE BRANCH COMES FROM THE STORE, NOT FROM THE CWD (#1721 Decision).
``resolve_issue_branch`` reads the branch the State Store binds the issue to — the
binding ``atdd worktree create`` writes and #1720 indexed in both directions. It
deliberately does NOT run ``git rev-parse --abbrev-ref HEAD``. Reading the branch
from the current directory would re-introduce, one layer up, exactly the coupling
#1376 removed: today the token's LOCATION is worktree-independent, and taking the
branch from cwd would make its VALIDITY worktree-dependent instead — the same
defect wearing a different hat, inside the program that exists to name it. See
``approve_command``'s #1376 comment: *one resolution at both ends is what makes the
token a receipt rather than a file whose visibility depends on which directory the
operator stood in.* That principle applies to the branch too.

WHAT THE BINDING THEREFORE CATCHES. Because both ends read the same store, this is
not a check on where a command was run. It is a check on DRIFT OVER TIME: a token
records the branch the issue was bound to when the operator approved, and stops
verifying once the issue is bound to a different one — a rename, a recreated
worktree, a re-pointed work item. The approval was for the work on that branch; if
the binding moved, the approval is stale. That refusal must SAY the branch changed
(``approval_check`` diagnoses it), because a refusal that cannot name its cause is
the defect this program is named for.

NOT A SECURITY BOUNDARY. ``resolve_signing_key`` falls back to a public constant,
so any process that can import ``approval`` can mint a correctly-branched, unexpired
token in one line. Branch and expiry close ACCIDENT and DRIFT. Read the THREAT MODEL
in :mod:`atdd.coach.gate.approval`; nothing here may be taken to contradict it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

#: ``external_refs`` coordinates of the GitHub issue projection (#1183) — the same
#: pair ``SmokeExecutionGateCheck`` and ``WorkItemReader`` resolve an issue by.
_GITHUB_PROVIDER = "github"
_ISSUE_REF_KIND = "issue"

#: The work-item ``data`` key ``atdd worktree create`` writes the branch under.
_BRANCH_KEY = "branch"

#: How long an operator approval stays valid (#1721 Decision).
#:
#: TWENTY-FOUR HOURS, and the number is a decision rather than a default. It spans
#: an overnight gap — an operator approving at the end of a day and a worker acting
#: the next morning is the longest delay a human-in-the-loop sign-off legitimately
#: has — while guaranteeing an approval cannot survive into a second working day's
#: tree, which is what makes it a bound rather than a decoration.
#:
#: MEASURED, not guessed. Across all seven approval tokens live on this machine on
#: 2026-08-04, the gap between the mint and the transition it authorised was 5s, 5s,
#: 7s, 10s, 17s, 18s and 84s. The widest observed need is 84 seconds, so 24h is
#: ~1000x the demonstrated requirement: this constrains STALENESS and cannot
#: plausibly cut a live flow short. (Those seven were agent self-mints, which is the
#: defect #1670 exists to fix; the headroom is sized for the human-approver regime
#: it is building toward, not for the one that produced the measurement.)
APPROVAL_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class BranchBinding:
    """The branch an issue is bound to, or a sayable reason there is none.

    Two fields rather than an ``Optional[str]`` because the three ways this can come
    back empty need three different operator actions — register the issue, record its
    branch, or fix the store — and a bare ``None`` collapses them into one
    unactionable refusal. :attr:`reason` is written to be printed verbatim.
    """

    branch: Optional[str] = None
    reason: Optional[str] = None

    def __bool__(self) -> bool:
        return bool(self.branch)


def resolve_issue_branch(start: Path, issue_number: int) -> BranchBinding:
    """The branch the State Store binds ``issue_number`` to.

    ``start`` is a STARTING POINT for Control-Root resolution, never the location
    itself — the same contract ``approval_paths`` keeps. Resolves through the
    ``external_refs`` GitHub projection exactly as ``SmokeExecutionGateCheck`` does,
    and reads ``data["branch"]`` off the work item.

    Never raises: a store fault comes back as a :class:`BranchBinding` carrying a
    reason. Callers must refuse on an empty binding, but the refusal they emit is a
    could-not-check, not a violation — the two are different facts and
    ``decision.run_checks`` would flatten a raised exception into ``FAIL``.
    """
    # Imported lazily so the gate package keeps importing without pulling the state
    # layer in — the deferred-import shape SmokeExecutionGateCheck established.
    from atdd.state.smoke_evidence import open_state_store

    try:
        with open_state_store(control_root=Path(start)) as store:
            ref = store.external_refs.resolve(
                _GITHUB_PROVIDER, _ISSUE_REF_KIND, str(int(issue_number))
            )
            if ref is None:
                return BranchBinding(
                    reason=(
                        f"#{issue_number} resolves to no work item in the State Store, "
                        f"so there is no branch to bind the approval to "
                        f"(register it with `atdd worktree create {issue_number}`)"
                    )
                )
            obj = store.objects.get(ref.object_uid)
            data = getattr(obj, "data", None)
            branch = (data or {}).get(_BRANCH_KEY) if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001 — reported as a reason, never raised
        logger.warning(
            "approval branch binding: the State Store could not be read",
            extra={"issue": issue_number, "start": str(start), "error": str(exc)},
        )
        return BranchBinding(
            reason=(
                f"the State Store under {start} could not be read, so the branch "
                f"#{issue_number} is bound to could not be observed: {exc}"
            )
        )

    if not branch:
        return BranchBinding(
            reason=(
                f"work item {ref.object_uid!r} (#{issue_number}) records no branch, "
                f"so there is no branch to bind the approval to "
                f"(re-register it with `atdd worktree create {issue_number}`)"
            )
        )
    return BranchBinding(branch=str(branch))


def expiry_for(approved_at: datetime) -> str:
    """The ISO-8601 instant an approval minted at ``approved_at`` stops verifying.

    A function rather than arithmetic at the call site so :data:`APPROVAL_TTL` has
    exactly one consumer, and so a test can assert the duration the mint actually
    applies instead of restating it.
    """
    return (approved_at + APPROVAL_TTL).isoformat()


__all__ = [
    "APPROVAL_TTL",
    "BranchBinding",
    "expiry_for",
    "resolve_issue_branch",
]
