# Acceptance: acc:govern-lifecycle:E050-UNIT-003-the-merge-waits-for-the-signed-phase
"""GT-003 — a PR that auto-closes an issue must not merge before REFACTOR (#1999).

`_BLOCKED_PHASES` is the set of phases a merge may NOT land in. It stops at GREEN, so a PR
carrying `Closes #N` merges while the issue sits at SMOKE — and `auto-phase` then advances
exactly one step, landing the code with the issue at REFACTOR and nobody having signed.

MEASURED, not hypothetical: PR #1991 merged 2026-09-13T09:22:45Z closing issue #1982, which
still reads SMOKE in the State Store. That merge was not merely unapproved — under a
signature sited at REFACTOR it is UNAPPROVABLE, because the mint refuses an edge the issue
is not standing on (`approve_command.py`, #1735).

Adding SMOKE here is not a second gate. It is what MAKES REFACTOR the gate: the only route
to a merge then runs through the phase where the operator signs (#1999 Decision 33 — filed
because the constant's name reads backwards and invited that confusion once already).

BLOCKED is deliberately absent: it is reversible and is how a worker surfaces a problem.

Convention: src/atdd/coach/conventions/pr.convention.yaml
            (rule coach.pr.merge-blocks-on-pre-smoke-close)
"""
from __future__ import annotations

import pytest

from atdd.coach.validators.test_pr_merge_blocks_pre_smoke_close import (
    _BLOCKED_PHASES,
    evaluate_pr_merge_violations,
)

pytestmark = [pytest.mark.coach]


def _resolution(phase: str) -> dict:
    """A PR resolution shaped like `PRManager.resolve_linked_issue` plus `pr_number`."""
    return {
        "pr_number": 1991,
        "issue_number": 1982,
        "phase_label": phase,
        "strategy": "body",  # a real auto-closing keyword, not weak inference
    }


def test_a_pr_closing_an_issue_at_smoke_is_refused() -> None:
    """The #1982 case: the merge must wait for REFACTOR."""
    violations = evaluate_pr_merge_violations([_resolution("SMOKE")])

    assert violations, (
        "a PR auto-closing an issue at SMOKE produced no violation, so it merges. "
        "PR #1991 did exactly this on 2026-09-13 and issue #1982 still reads SMOKE. "
        "The merge must wait for REFACTOR, which is where the operator signs."
    )


def test_smoke_is_in_the_blocked_set() -> None:
    """Stated directly, so the refusal above cannot pass for an unrelated reason."""
    assert "SMOKE" in _BLOCKED_PHASES, (
        f"_BLOCKED_PHASES is {sorted(_BLOCKED_PHASES)}; SMOKE is absent, so a merge may "
        "land one step before the gate it is supposed to wait for."
    )


def test_refactor_still_merges() -> None:
    """REFACTOR is the phase a merge is FOR — blocking it would stop every merge."""
    assert not evaluate_pr_merge_violations([_resolution("REFACTOR")]), (
        "REFACTOR was blocked. It is the phase the operator signs at and merges from; "
        "blocking it makes every issue unmergeable."
    )


def test_blocked_is_not_in_the_blocked_set() -> None:
    """An escape a worker enters to report a problem is not a merge-phase question."""
    assert "BLOCKED" not in _BLOCKED_PHASES, (
        "BLOCKED joined the merge-blocked set. It is reversible and is how a worker "
        "surfaces a problem; it is governed by its exits, not by this rule."
    )
