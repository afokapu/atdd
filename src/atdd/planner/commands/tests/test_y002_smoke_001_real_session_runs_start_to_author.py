# URN: test:define-plans:atdd-plan-session:Y002-SMOKE-001-real-session-runs-start-to-author
# Acceptance: acc:define-plans:Y002-SMOKE-001-real-session-runs-start-to-author
# WMBT: wmbt:define-plans:Y002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""Y002-SMOKE-001 — a REAL `atdd plan` session runs start -> author under the new names.

Drives the installed CLI over subprocess (`python -m atdd plan ...`), no mocks
and no in-process `run()` call: a unit test over the `Step` enum would pass
while the CLI still printed the old words, which is the whole reason this
acceptance exists.

The session walks Intent -> Attach -> Compose -> Ratify -> author using ONLY the
new stage names, and the run is asserted to land real artifacts on disk rather
than merely exiting zero.

The kept unit is a wagon named `manage-users` because the Ratify gate runs the
#1276 verb-object check on kept wagon units — a non-verb-object slug would be
refused before the lock and this smoke would prove nothing about the rename.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[4]

_WAGON_SPEC = {
    "wagon": "manage-users",
    "description": "manage users end to end for the stage-rename smoke",
    "subject": "agent:planner",
    "context": "smoke",
    "action": "manages users",
    "goal": "users are managed",
    "outcome": "user records are consistent",
    "produce": [{"name": "commons:user:record"}],
}

# Retired STAGE names. `confirm` is deliberately excluded from the lowercase
# sweep: it survives legitimately as the alias listed in help output and inside
# the rule name `confirm-before-author`. The capitalised stage words are what
# must be gone from operator-facing output.
RETIRED_STAGE_WORDS = ("Define", "Locate", "Prepare")


def _sess(root: Path, *args):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(root)}
    return subprocess.run(
        [sys.executable, "-m", "atdd", "plan", "--root", str(root), *args],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=120)


def _ok(r):
    assert r.returncode == 0, f"exit {r.returncode}\nstdout={r.stdout}\nstderr={r.stderr}"
    return r


def _state(r):
    _ok(r)
    lines = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip().startswith("{")]
    assert lines, f"no JSON state emitted\nstdout={r.stdout}\nstderr={r.stderr}"
    return json.loads(lines[-1])


@pytest.fixture()
def session(tmp_path):
    """A real session driven start -> author, returning every transcript line."""
    (tmp_path / "plan").mkdir(exist_ok=True)
    sid = "y002-smoke"
    transcript = []

    def step(*args):
        r = _sess(tmp_path, *args)
        transcript.append(r.stdout + r.stderr)
        return r

    states = {}
    states["start"] = _state(step("start", "--id", sid, "--main-job",
                                 "rename the plan-session stages", "--issue", "local:1688"))
    states["attach"] = _state(step("advance", "--id", sid, "--step", "attach"))
    step("source", "--id", sid, "the measured blast radius")
    states["compose"] = _state(step("advance", "--id", sid, "--step", "compose"))
    step("unit", "--id", sid, "--kind", "wagon", "--ref", "manage-users",
         "--spec", json.dumps(_WAGON_SPEC))
    states["ratify_stage"] = _state(step("advance", "--id", sid, "--step", "ratify"))
    step("decide", "--id", sid, "--ref", "manage-users", "--verdict", "keep")
    states["locked"] = _state(step("ratify", "--id", sid))
    states["authored"] = _state(step("author", "--id", sid))
    return {"root": tmp_path, "states": states, "transcript": transcript}


def test_the_session_walks_the_new_stages_in_order(session):
    st = session["states"]
    assert st["start"]["step"] == "intent"
    assert st["attach"]["step"] == "attach"
    assert st["compose"]["step"] == "compose"
    assert st["ratify_stage"]["step"] == "ratify"


def test_ratify_locks_and_author_completes(session):
    st = session["states"]
    assert st["locked"]["locked"] is True, "the Ratify gate did not lock the session"
    assert st["authored"]["step"] == "authored"


def test_the_run_lands_real_artifacts_on_disk(session):
    """Exit zero is not the assertion — the authored files are."""
    authored = session["states"]["authored"].get("authored") or []
    assert authored, "author reported success but named no artifact"
    for path in authored:
        assert Path(path).is_file(), f"authored path does not exist on disk: {path}"


def test_no_output_along_the_way_names_a_retired_stage(session):
    for chunk in session["transcript"]:
        for word in RETIRED_STAGE_WORDS:
            assert word not in chunk, f"CLI output still names the retired stage {word!r}: {chunk}"


def test_the_retired_step_values_are_rejected_by_the_real_cli(tmp_path):
    """The other half of the rename reaching the CLI: old spellings are gone."""
    (tmp_path / "plan").mkdir(exist_ok=True)
    _ok(_sess(tmp_path, "start", "--id", "old", "--main-job", "job", "--issue", "local:1688"))
    r = _sess(tmp_path, "advance", "--id", "old", "--step", "locate")
    assert r.returncode != 0, "the real CLI still accepts --step locate"
    assert "invalid choice" in (r.stdout + r.stderr)
