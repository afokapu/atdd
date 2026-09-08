# URN: test:drive-state-machine:post-merge-advance-is-observable:C001-UNIT-002-an-unobservable-link-fails-the-run
# Acceptance: acc:drive-state-machine:C001-UNIT-002-an-unobservable-link-fails-the-run
# WMBT: wmbt:drive-state-machine:C001
# Phase: RED
# Layer: application
"""C001-UNIT-002 — an advance that could not be attempted must fail the run.

#1452 already established the principle in this very function: a `divergence`
exits 1, because "silence is what let 236 records accumulate — auto-phase exited
0 on a label it did not write". An unreadable link is the same silence one step
earlier, and still exits 0. It stayed invisible until someone read
a phase label days later — which is how this looked "intermittent" rather than
broken.
"""
from __future__ import annotations

from atdd.coach.commands import auto_phase as ap


def _result(action, reason, issue=None):
    return ap.AutoPhaseResult(
        pr_number=1806, issue_number=issue, current_phase=None,
        next_phase=None, action=action, reason=reason,
    )


def test_an_unreadable_link_exits_non_zero(monkeypatch, capsys):
    monkeypatch.setattr(ap, "resolve_pr_to_transition", lambda *a, **k: _result(
        "unreadable", "could not fetch PR #1806: gh exited 1"))

    rc = ap.run(1806)

    assert rc != 0, (
        "the advance could not even be attempted; exiting 0 tells CI the "
        "post-merge step succeeded when nothing was done"
    )
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "no-op" not in out.lower(), (
        "an unobservable link is not a no-op; saying so is the false statement "
        "this issue exists to remove"
    )


def test_a_genuine_no_op_still_exits_zero(monkeypatch):
    """The guard: a PR that owes nothing must keep passing."""
    monkeypatch.setattr(ap, "resolve_pr_to_transition", lambda *a, **k: _result(
        "noop", "no linked issue"))

    assert ap.run(1806) == 0
