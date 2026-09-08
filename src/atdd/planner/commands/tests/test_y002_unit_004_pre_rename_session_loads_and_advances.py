# URN: test:define-plans:atdd-plan-session:Y002-UNIT-004-pre-rename-session-loads-and-advances
# Acceptance: acc:define-plans:Y002-UNIT-004-pre-rename-session-loads-and-advances
# WMBT: wmbt:define-plans:Y002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""Y002-UNIT-004 — a session.json written before the rename still works.

`PlanSession.load()` is `cls(**data)` with no validation, so a stale stage value
loads fine and the *next* `Step(self.step)` — in advance(), reopen() or
confirm() — raises a bare `ValueError`. `ValueError` is not `SessionGateError`,
so it escapes the CLI's handler and reaches the operator as a traceback rather
than a refusal.

`.atdd/runtime/` is gitignored, so these sessions are machine-local and there is
no distributed migration burden — but they are real: 14 of them existed across
8 worktrees when this was measured, carrying every one of the four retired
values.

RED: `load()` has no legacy alias map.
"""
from __future__ import annotations

import json

import pytest

from atdd.planner.commands.plan_session import PlanSession, SessionGateError, Step

# The pre-rename value -> the stage it now means.
LEGACY_TO_NEW = {
    "define": "intent",
    "locate": "attach",
    "prepare": "compose",
    "confirm": "ratify",
}


def _write_session(root, session_id: str, step: str):
    path = root / ".atdd" / "runtime" / "plan-sessions" / session_id / "session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "session_id": session_id,
        "step": step,
        "main_job": "a job written before the rename",
        "sources": [{"type": "text", "value": "spec"}],
        "units": [],
        "locked": False,
        "issue_ref": None,
    }, indent=2, sort_keys=True), encoding="utf-8")
    return path


@pytest.mark.parametrize("legacy,new", sorted(LEGACY_TO_NEW.items()))
def test_pre_rename_session_loads_under_the_new_stage_name(tmp_path, legacy, new):
    _write_session(tmp_path, f"legacy-{legacy}", legacy)
    s = PlanSession.load(f"legacy-{legacy}", tmp_path)
    assert s.step == new


@pytest.mark.parametrize("legacy", sorted(LEGACY_TO_NEW))
def test_pre_rename_session_advances_without_valueerror(tmp_path, legacy):
    """The defect this fixes: the traceback lands on the *next* call, not load()."""
    _write_session(tmp_path, f"adv-{legacy}", legacy)
    s = PlanSession.load(f"adv-{legacy}", tmp_path)
    try:
        s.advance(Step(s.step))  # no-op advance; exercises Step(self.step)
    except ValueError as exc:
        pytest.fail(f"pre-rename session {legacy!r} raised ValueError: {exc}")
    except SessionGateError:
        pass  # a refusal is fine; it reaches the operator as a message


@pytest.mark.parametrize("legacy", sorted(LEGACY_TO_NEW))
def test_pre_rename_session_round_trips_through_save(tmp_path, legacy):
    """Loading normalises, so the stale value does not survive the next save."""
    _write_session(tmp_path, f"rt-{legacy}", legacy)
    s = PlanSession.load(f"rt-{legacy}", tmp_path)
    s.save(tmp_path)
    on_disk = json.loads(
        (tmp_path / ".atdd" / "runtime" / "plan-sessions" / f"rt-{legacy}"
         / "session.json").read_text(encoding="utf-8"))
    assert on_disk["step"] == LEGACY_TO_NEW[legacy]


def test_authored_still_loads_unchanged(tmp_path):
    """AUTHORED did not move, so it must not be aliased to anything."""
    _write_session(tmp_path, "authored-session", "authored")
    s = PlanSession.load("authored-session", tmp_path)
    assert s.step == Step.AUTHORED.value == "authored"


def test_an_unknown_stage_value_is_still_refused(tmp_path):
    """The alias map must not become a catch-all that swallows real corruption."""
    _write_session(tmp_path, "bogus-session", "not-a-stage")
    s = PlanSession.load("bogus-session", tmp_path)
    with pytest.raises(ValueError):
        Step(s.step)
