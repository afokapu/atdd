# URN: test:drive-state-machine:post-merge-advance-is-observable:C002-UNIT-002-the-refusal-names-the-merge-not-an-absent-link
# Acceptance: acc:drive-state-machine:C002-UNIT-002-the-refusal-names-the-merge-not-an-absent-link
# WMBT: wmbt:drive-state-machine:C002
# Phase: RED
# Layer: application
"""C002-UNIT-002 — the refusal states the cause it OBSERVED, not one it assumed.

THIS IS THE ACCEPTANCE THAT CANNOT BE ASSERTED ON `action`, and the reason is
measured rather than argued.

Applying #2004's fix exactly as it was first worded — "`read_linked_issue`
returns a refusal when `mergedAt` is null" — and driving it through `run()`
produced, 2026-09-13:

    CANDIDATE  state=OPEN    action=noop   'PR #9002: no-op - no linked issue'
    CANDIDATE  state=CLOSED  action=noop   'PR #9002: no-op - no linked issue'

The advance stopped, 2 of 2. And the operator was told the pull request links no
issue, about a pull request whose body reads `Closes #9001`.
`auto_phase.resolve_pr_to_transition` hardcodes `reason="no linked issue"` for
any reading with a null payload (`auto_phase.py:134`), so the refusal written in
`read_linked_issue` never reaches stdout.

Done-when for #2004 is "transitions nothing AND SAYS WHY". A test asserting only
`action != "transition"` passes against that version — the one that stops the
advance and states a falsehood. So every assertion here is on the PRINTED TEXT.

This is #1640's split one layer on: "could not read", "nothing to read" and
"read it, and it has not merged" are three different answers, and the third must
not collapse into the second.
"""
from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import pytest

from atdd.coach.commands import auto_phase as ap
from atdd.coach.commands.pr import PRManager

ISSUE, PR = 9001, 9002


def _payload(state, merged_at):
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
def run_cli(monkeypatch):
    """Drive `run()` and return exactly what an operator reads."""
    def _run(state, merged_at, phase="SMOKE"):
        monkeypatch.setattr(PRManager, "_read_pr",
                            lambda self, n: (_payload(state, merged_at), None))
        monkeypatch.setattr(PRManager, "_fetch_issue",
                            lambda self, n: {"number": ISSUE,
                                             "labels": [{"name": "atdd-issue"},
                                                        {"name": f"atdd:{phase}"}]})
        # dry_run so a transition never shells out to `atdd coach transition`.
        out, err = io.StringIO(), io.StringIO()
        with (tempfile.TemporaryDirectory() as tmp,
              redirect_stdout(out), redirect_stderr(err)):
            rc = ap.run(PR, dry_run=True, target_dir=Path(tmp))
        return rc, (out.getvalue() + err.getvalue()).strip()
    return _run


@pytest.mark.parametrize("state", ["OPEN", "CLOSED"])
def test_the_printed_line_names_the_merge(run_cli, state):
    _rc, text = run_cli(state, None)

    assert "merge" in text.lower(), (
        "the line an operator reads does not mention the merge, so it does not "
        "say why nothing advanced. Done-when is 'transitions nothing AND says "
        f"why'. got: {text!r}"
    )


@pytest.mark.parametrize("state", ["OPEN", "CLOSED"])
def test_the_printed_line_does_not_claim_the_link_is_absent(run_cli, state):
    """The measured trap: a true refusal carrying a false cause."""
    _rc, text = run_cli(state, None)

    assert "no linked issue" not in text, (
        "the refusal says the pull request links no issue, about a pull request "
        "whose body reads 'Closes #9001'. `auto_phase.py:134` replaces the "
        "reading's own reason with that literal. Stopping the advance while "
        f"naming a cause that is false is not the Done-when. got: {text!r}"
    )


def test_open_and_closed_read_differently(run_cli):
    """An open PR and a declined one need different operator actions.

    `mergedAt` is null for both, so it cannot tell them apart — `state` is the
    only field that carries the distinction, and it is already in the payload.
    """
    _rc_open, open_text = run_cli("OPEN", None)
    _rc_closed, closed_text = run_cli("CLOSED", None)

    assert open_text != closed_text, (
        "an open pull request and one closed without merging produce the same "
        "line. Waiting for a merge and re-opening a declined PR are different "
        f"next actions. got: {open_text!r}"
    )
    assert "OPEN" in open_text, f"the open case does not name its state: {open_text!r}"
    assert "CLOSED" in closed_text, f"the closed case does not name its state: {closed_text!r}"


def test_not_merged_is_distinguishable_from_could_not_read(run_cli, monkeypatch):
    """The third answer must not collapse into the FIRST one either (#1640).

    An unreadable PR already fails the run loudly. "Read it, and it has not
    merged" is an ordinary mistake, not a fault — #2004 Decision 2 — so it must
    not borrow the unreadable path's exit code or its words.
    """
    rc_unmerged, unmerged_text = run_cli("OPEN", None)

    monkeypatch.setattr(PRManager, "_read_pr",
                        lambda self, n: (None, "gh pr view exited 1: boom"))
    out, err = io.StringIO(), io.StringIO()
    with (tempfile.TemporaryDirectory() as tmp,
          redirect_stdout(out), redirect_stderr(err)):
        rc_unreadable = ap.run(PR, dry_run=True, target_dir=Path(tmp))
    unreadable_text = (out.getvalue() + err.getvalue()).strip()

    assert rc_unreadable != 0, "an unreadable PR must still fail the run (#1640)"
    assert rc_unmerged == 0, (
        "a not-yet-merged PR is a no-op with a reason, not a fault (#2004 "
        f"Decision 2). got exit {rc_unmerged}"
    )
    assert unmerged_text != unreadable_text, (
        "'it has not merged' and 'I could not look' print the same thing; they "
        "are different observations with different operator actions"
    )
