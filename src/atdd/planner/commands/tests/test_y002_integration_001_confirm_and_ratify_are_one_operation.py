# URN: test:define-plans:atdd-plan-session:Y002-INTEGRATION-001-confirm-and-ratify-are-one-operation
# Acceptance: acc:define-plans:Y002-INTEGRATION-001-confirm-and-ratify-are-one-operation
# WMBT: wmbt:define-plans:Y002
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""Y002-INTEGRATION-001 — `atdd plan confirm` and `atdd plan ratify` are one operation.

The alias IS the deprecation window, so it has to do the work, not merely be
accepted. This is the failure mode worth spending a test on:

argparse sets the subparser dest to the name the operator TYPED, not the
canonical parser name. With `add_parser("ratify", aliases=["confirm"])`, typing
`confirm` yields `args.op == "confirm"` and typing `ratify` yields `"ratify"`.
A dispatch that tests only for `"ratify"` therefore lets `atdd plan confirm`
fall through the whole if/elif chain to `s.save(root)`, print the session state,
and exit ZERO with the session still unlocked — success reported without acting.

So this drives the real CLI and asserts on the resulting state, not on the exit
code alone.

RED: there is no `ratify` subcommand.
"""
from __future__ import annotations

import json

import pytest

from atdd.planner.commands.plan_session import PlanSession
from atdd.planner.commands.plan_session_cli import run

LOCK_SPELLINGS = ["ratify", "confirm"]


def _drive_to_ratify(root, session_id: str) -> None:
    """Take a session to the lock boundary with one kept unit and a bound issue.

    The kept unit is a `wmbt`, which no confirm-time validation claims: the
    interlocking, verb-object and artifact-naming gates look at kept train,
    wagon and feature units. This isolates the alias from those gates.
    """
    argv = ["--root", str(root)]
    assert run(argv + ["start", "--id", session_id, "--main-job", "rename the stages",
                       "--issue", "local:1688"]) == 0
    assert run(argv + ["advance", "--id", session_id, "--step", "attach"]) == 0
    assert run(argv + ["source", "--id", session_id, "the measured blast radius"]) == 0
    assert run(argv + ["advance", "--id", session_id, "--step", "compose"]) == 0
    assert run(argv + ["unit", "--id", session_id, "--kind", "wmbt",
                       "--ref", "wmbt:define-plans:Z001", "--spec", "{}"]) == 0
    assert run(argv + ["advance", "--id", session_id, "--step", "ratify"]) == 0
    assert run(argv + ["decide", "--id", session_id, "--ref", "wmbt:define-plans:Z001",
                       "--verdict", "keep"]) == 0


@pytest.mark.parametrize("spelling", LOCK_SPELLINGS)
def test_each_spelling_actually_locks_the_session(tmp_path, spelling):
    """Exit zero is not the assertion. The lock is."""
    sid = f"y002-lock-{spelling}"
    _drive_to_ratify(tmp_path, sid)
    assert run(["--root", str(tmp_path), spelling, "--id", sid]) == 0
    assert PlanSession.load(sid, tmp_path).locked is True, (
        f"`atdd plan {spelling}` exited 0 without locking the session")


def test_both_spellings_emit_identical_state(tmp_path, capsys):
    """Same operation, so the projected state must match field for field."""
    emitted = {}
    for spelling in LOCK_SPELLINGS:
        sid = f"y002-same-{spelling}"
        _drive_to_ratify(tmp_path, sid)
        capsys.readouterr()
        assert run(["--root", str(tmp_path), spelling, "--id", sid]) == 0
        emitted[spelling] = json.loads(capsys.readouterr().out)

    ratified, confirmed = emitted["ratify"], emitted["confirm"]
    assert ratified.pop("session_id") != confirmed.pop("session_id")
    assert ratified == confirmed


@pytest.mark.parametrize("spelling", LOCK_SPELLINGS)
def test_each_spelling_refuses_through_the_same_non_zero_path(tmp_path, spelling):
    """A gate refusal must reach exit 2 either way — an alias that swallowed the
    refusal would be the same defect wearing the opposite face."""
    sid = f"y002-refuse-{spelling}"
    argv = ["--root", str(tmp_path)]
    # Bound to an issue but with an undecided unit: confirm must refuse.
    assert run(argv + ["start", "--id", sid, "--main-job", "job", "--issue", "local:1688"]) == 0
    assert run(argv + ["advance", "--id", sid, "--step", "attach"]) == 0
    assert run(argv + ["source", "--id", sid, "a source"]) == 0
    assert run(argv + ["advance", "--id", sid, "--step", "compose"]) == 0
    assert run(argv + ["unit", "--id", sid, "--kind", "wmbt",
                       "--ref", "wmbt:define-plans:Z002", "--spec", "{}"]) == 0
    assert run(argv + ["advance", "--id", sid, "--step", "ratify"]) == 0

    assert run(argv + [spelling, "--id", sid]) == 2
    assert PlanSession.load(sid, tmp_path).locked is False
