"""Which commit an approval for an issue would be granted for (#1765).

Split out of ``mint_gate`` so the mint decision and the head resolution are
separate concerns, and because ``mint_gate`` crossed the 500-line file limit when
this logic landed in it.

NAMED ``resolve_issue_head``, NOT ``resolve_head``. ``atdd.state.reconcile`` already
has a ``resolve_head(repo)`` returning the repository's HEAD; this one takes
``(start, issue_number)`` and returns the head of the branch the State Store binds
to that issue. Two different edges. #1755 records seven resolvers over these graph
edges with two pairs already sharing a name across incompatible signatures, and
#1754 established that for such a pair the remedy is a RENAME rather than a
collapse, because the duplication is correct and the shared name is the defect.
Shipping a third collision out of the very fix that cites #1755 was not defensible.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from atdd.coach.gate.approval_binding import resolve_issue_branch

logger = logging.getLogger(__name__)

_GIT_TIMEOUT_S = 10


@dataclass(frozen=True)
class HeadBinding:
    """The commit the approval would be granted for, or a sayable reason there is none.

    The same shape and the same discipline as
    :class:`~atdd.coach.gate.approval_binding.BranchBinding`, for the same reason:
    the ways this comes back empty need different operator actions — register the
    issue, record its branch, fetch the branch into this repository, fix the store
    — and a bare ``None`` collapses them into one unactionable refusal. What is
    NOT collapsed either way is "could not resolve" against "resolved to nothing";
    both are unmade observations and neither may read as a clean answer.

    :attr:`branch` is the branch that WAS found when one was, so a refusal on the
    step after can name it.
    """

    sha: Optional[str] = None
    branch: Optional[str] = None
    reason: Optional[str] = None

    def __bool__(self) -> bool:
        return bool(self.sha)


def _branch_head(start: Path, branch: str) -> Optional[str]:
    """The commit ``refs/heads/<branch>`` names, read from the repo at ``start``.

    ``start`` selects the REPOSITORY, never the tree — and that distinction is the
    whole of #1765. Every linked worktree of a repository shares one ``refs/``
    namespace, so ``rev-parse refs/heads/<branch>`` returns the same commit from
    all of them while ``rev-parse HEAD`` returns a different one in each. Asking
    for the named ref is what makes the answer a property of the issue rather than
    of where the operator was standing.

    ``--verify --quiet`` with the full ``refs/heads/`` prefix so an unknown branch
    is exit 1 and silence rather than a partial match or a flag; ``^{commit}``
    peels an annotated-tag-shaped ref to the commit the gates would run against.
    ``None`` for every fault, which the caller turns into a refusal — no fallback
    to ``HEAD`` exists here, because falling back is the defect.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--verify", "--quiet",
             f"refs/heads/{branch}^{{commit}}"],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug(
            "conditional mint: cannot resolve the issue's branch head",
            extra={"start": str(start), "branch": branch, "error": str(exc)},
        )
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _remote_head(start: Path, branch: str) -> Optional[str]:
    """The commit ``refs/remotes/origin/<branch>`` names, read from ``start``.

    The REVIEWED head. ``_branch_head`` reads the LOCAL ref, which is whatever
    this clone last committed — not what the operator looked at.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--verify", "--quiet",
             f"refs/remotes/origin/{branch}^{{commit}}"],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug(
            "reviewed head: cannot resolve the remote-tracking ref",
            extra={"start": str(start), "branch": branch, "error": str(exc)},
        )
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


# THE COMMIT THE OPERATOR REVIEWED, NOT THE ONE THIS CLONE HAPPENS TO HOLD (#2005).
#
# ``_branch_head`` reads ``refs/heads/<branch>``. The operator reviews the diff
# and the CI run on the PULL REQUEST, which is the remote head. Measured
# 2026-09-13 across all 23 open pull requests in this repository: the local ref
# equalled the reviewed head 11 times out of 14, and of the 3 misses TWO had the
# local ref AHEAD — by 3 commits and by 1 — and one was genuinely diverged.
#
# So in two of three the mint would have attested commits that were never pushed:
# CI never ran on them, the reviewer never saw them, and they are not what merges.
# That failure is silent and in the worst direction. Today the token claims no
# commit at all; recording the local ref would make it claim a specific WRONG one,
# with nothing printed. A manufactured attestation is worse than an absent one,
# which is why this refuses rather than falling back to ``_branch_head``.
def resolve_reviewed_head(start: Path, branch: str) -> HeadBinding:
    """The commit an approval for ``branch`` would attest, or a sayable refusal.

    Returns the REMOTE-tracking head — what the pull request shows and what CI
    reported against. Never falls back to the local ref: falling back is the
    defect, the same reasoning ``_branch_head`` applies to ``HEAD``.
    """
    remote = _remote_head(start, branch)
    if remote is None:
        return HeadBinding(
            branch=branch,
            reason=(
                f"no remote-tracking ref refs/remotes/origin/{branch} could be "
                f"read in the repository at {start}, so the commit the operator "
                f"reviewed could not be established (push the branch, or fetch it "
                f"here, before approving)"
            ),
        )
    return HeadBinding(sha=remote, branch=branch)


# WHY ``resolve_issue_head`` LOOKS THE WAY IT DOES (#1765).
#
# THE ISSUE'S HEAD, NOT THE OPERATOR'S. This used to shell ``git rev-parse HEAD``
# in the invoking directory, so on 2026-08-08 two approvals were evaluated against
# the head of a third, unrelated branch — the one the orchestrator's shell was
# sitting in. The branch is resolved through the State Store binding by #1721 and
# the edge's legality by #1735; this was the one field still taken from the cwd,
# which made the mint's output internally inconsistent: it named one branch and
# attested a commit from another.
#
# So the commit is resolved the way the branch already is, by REUSING
# ``approval_binding.resolve_issue_branch`` — #1755 records seven functions
# resolving these same graph edges already, two pairs of them sharing a name with
# incompatible signatures, and adding an eighth to fix a cwd-coupling bug would be
# the defect that issue exists to name. ``start`` is a STARTING POINT for
# Control-Root and repository resolution, never the location itself, which is the
# contract ``approval_paths`` and ``approval_binding`` both keep.
#
# SEPARATE FROM ``SmokeExecutionGateCheck._head_sha`` ON PURPOSE, and the
# difference is a policy one rather than an oversight. That function returns
# ``None`` when git is silent and ``evaluate_smoke_execution`` then disables its
# staleness clause ENTIRELY — deliberate, and its own docstring argues it: "an
# unresolvable HEAD is an environment fault, and turning it into 'smoke did not
# run' would make the gate unfixable rather than fail-closed."
#
# For a GATE that is defensible. For a MINT it means the evidence's binding to the
# tree is silently switched off and a signed authorisation is written anyway — "I
# could not look at whether this evidence is stale" passing as "the evidence is
# current", which is #1670's condition 3 in the place it is easiest to miss,
# because nothing fails and nothing is printed.
#
# So the mint asks the question itself and refuses on an empty binding, and
# ``SmokeExecutionGateCheck`` is left exactly as it is: strictness is added where
# the authorisation is written, not taken out of the transition gate, where it
# would change behaviour repo-wide for every issue in every non-git environment.
#
# Kept as a comment rather than a docstring deliberately: ``coder.refactor
# .complexity-length`` counts docstring lines as code and skips ``#`` lines, so a
# thoroughly documented 18-line function scored 54 against a 50 limit. The
# reasoning is unabridged; only its form moved. The rule's own miscount is filed
# separately — do NOT "tidy" this back into the docstring without reading that.
def resolve_issue_head(start: Path, issue_number: int) -> HeadBinding:
    """The commit the approval for ``issue_number`` would be granted for.

    THE ISSUE'S HEAD, NOT THE OPERATOR'S — see the comment block above for why,
    and why this is deliberately separate from ``SmokeExecutionGateCheck``.

    Never raises, for ``resolve_issue_branch``'s reason: a store fault comes back
    as a binding carrying the fault, so "could not resolve" stays distinguishable
    from "resolved to nothing", and ``decision.run_checks`` cannot flatten a
    raised exception into a ``FAIL`` that would read as an observed violation.
    """
    binding = resolve_issue_branch(start, issue_number)
    if not binding:
        return HeadBinding(reason=binding.reason)

    sha = _branch_head(start, binding.branch)
    if sha is None:
        return HeadBinding(
            branch=binding.branch,
            reason=(
                f"the State Store binds #{issue_number} to branch "
                f"{binding.branch!r}, but no commit could be read for "
                f"refs/heads/{binding.branch} in the repository at {start} "
                f"(fetch or create the branch there, or re-register the issue "
                f"with `atdd worktree create {issue_number}`)"
            ),
        )
    return HeadBinding(sha=sha, branch=binding.branch)
