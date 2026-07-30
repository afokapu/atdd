"""Scope a PR-scanning gate's violations to the PR actually under validation (#1478).

Two strict gates — ``coach.pr.merge-blocks-on-pre-smoke-close`` and
``coach.pr.closes-keyword-discipline`` — scan every open PR in the repository. Without
scoping, one offending PR reds every other contributor's CI, which is cross-PR coupling
rather than enforcement: the branch being validated is failed for a state it neither
created nor can fix.

Both gates encode the offending PR in the violation ``location``, but not in the same
shape — the pre-SMOKE gate emits ``PR#<n>:0`` while the closes-keyword gate emits
``PR#<n>:body`` or ``PR#<n>:commit:<sha>``. Matching therefore keys on the ``PR#<n>:``
prefix, never on a whole-string equality that only one of the two would satisfy.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from atdd.coach.validators._violation import Violation


def pr_location_prefix(pr_number: int) -> str:
    """The ``location`` prefix every violation belonging to *pr_number* carries."""
    return f"PR#{pr_number}:"


def violations_for_pr(
    violations: Sequence[Violation], pr_number: int,
) -> List[Violation]:
    """Just the violations whose location names *pr_number*."""
    prefix = pr_location_prefix(pr_number)
    return [v for v in violations if str(v.location or "").startswith(prefix)]


def select_for_current_pr(
    violations: Sequence[Violation], current_pr: Optional[int],
) -> List[Violation]:
    """The violations that should FAIL a strict PR-scanning gate on this run.

    ``current_pr is None`` means the run cannot name its own PR — a push-event run
    whose branch leg found no open PR, a branch before its PR exists, a local
    repo-health run. That is advisory-only: nothing blocks. Blocking there would fail
    the run on a stranger's offense, and the offender is still blocked on the run that
    CAN name it.
    """
    if current_pr is None:
        return []
    return violations_for_pr(violations, current_pr)


__all__ = ["pr_location_prefix", "violations_for_pr", "select_for_current_pr"]
