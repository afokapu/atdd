# URN: test:drive-state-machine:post-merge-advance-is-observable:C002-UNIT-001-an-unmerged-pull-request-advances-nothing
# Acceptance: acc:drive-state-machine:C002-UNIT-001-an-unmerged-pull-request-advances-nothing
# WMBT: wmbt:drive-state-machine:C002
# Phase: RED
# Layer: application
"""C002-UNIT-001 — the merge is what authorises the advance, and it is consulted.

`PRManager._read_pr` requests `state` and `mergedAt` (`pr.py:245-249`);
`read_linked_issue` (`pr.py:313-341`) reads neither. Measured 2026-09-13 across
three PR states and seven phases: the shipped resolver returned BYTE-IDENTICAL
results for `OPEN`, `CLOSED`-unmerged and `MERGED`, producing 8 transitions out
of pull requests that never merged.

The three states are driven through the real `resolve_pr_to_transition` with only
`gh` stubbed, because the defect is in what the resolver does with a payload it
already has — stubbing the resolver would answer a different question.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from atdd.coach.commands import auto_phase as ap
from atdd.coach.commands.pr import PRManager

ISSUE, PR = 9001, 9002


def _payload(state, merged_at):
    """The exact shape `gh pr view --json ...,state,...,mergedAt` returns."""
    return {
        "number": PR,
        "title": f"feat: something (#{ISSUE})",
        "body": f"Closes #{ISSUE}",
        "headRefName": "feat/c002-lab",
        "state": state,
        "closingIssuesReferences": [{"number": ISSUE}],
        "mergedAt": merged_at,
    }


@pytest.fixture
def drive(monkeypatch):
    """Run the real resolver against one stubbed PR shape.

    The State Store is pointed at an empty directory so `read_store_phase`
    returns None and the label is the phase — the same fall-back the live path
    takes for an issue the store has never seen.
    """
    def _run(state, merged_at, phase="SMOKE"):
        monkeypatch.setattr(PRManager, "_read_pr",
                            lambda self, n: (_payload(state, merged_at), None))
        monkeypatch.setattr(PRManager, "_fetch_issue",
                            lambda self, n: {"number": ISSUE,
                                             "labels": [{"name": "atdd-issue"},
                                                        {"name": f"atdd:{phase}"}]})
        with tempfile.TemporaryDirectory() as tmp:
            return ap.resolve_pr_to_transition(PR, target_dir=Path(tmp))
    return _run


def test_an_open_pull_request_advances_nothing(drive):
    result = drive("OPEN", None)

    assert result.action != "transition", (
        "an open pull request advanced the lifecycle. The advance is authorised "
        "by the MERGE, and `mergedAt` is null — the fact is already on hand in "
        f"the same payload and was not consulted. got action={result.action!r} "
        f"{result.current_phase} -> {result.next_phase}"
    )
    assert result.next_phase is None


def test_a_closed_but_unmerged_pull_request_advances_nothing(drive):
    """A declined PR is closed and merged nothing. It must advance nothing."""
    result = drive("CLOSED", None)

    assert result.action != "transition", (
        "a pull request closed WITHOUT merging advanced the lifecycle. Closing "
        "is not merging; `mergedAt` is null for both a declined PR and an open "
        f"one. got action={result.action!r} -> {result.next_phase}"
    )
    assert result.next_phase is None


def test_a_merged_pull_request_still_advances(drive):
    """The path that works must not change — this is the regression guard."""
    result = drive("MERGED", "2026-09-13T09:22:45Z")

    assert result.action == "transition", (
        "a merged pull request must advance exactly as it does today; the fix "
        f"must not break the working path. got action={result.action!r}"
    )
    assert (result.current_phase, result.next_phase) == ("SMOKE", "REFACTOR")


def test_the_three_states_are_not_all_identical(drive):
    """The whole defect in one assertion.

    Measured: the shipped resolver's output is byte-identical across the three
    states. A fix that leaves them identical has changed nothing, whatever else
    it reports.
    """
    results = {s: drive(s, m) for s, m in
               (("OPEN", None), ("CLOSED", None), ("MERGED", "2026-09-13T09:22:45Z"))}
    actions = {s: r.action for s, r in results.items()}

    assert len(set(actions.values())) > 1, (
        "the resolver returns the same action for an open, a closed-unmerged and "
        f"a merged pull request: {actions}. The merge fact influences nothing."
    )
    assert actions["MERGED"] == "transition"
    assert actions["OPEN"] != "transition" and actions["CLOSED"] != "transition"
