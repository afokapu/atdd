# URN: test:define-plans:atdd-plan-session:SMOKE-live
# Issue: #1209
# Phase: SMOKE
# Layer: integration
# Acceptance: acc:define-plans:D001-SMOKE-001-seed
# Acceptance: acc:define-plans:L001-SMOKE-001-seed
# Acceptance: acc:define-plans:P001-SMOKE-001-seed
# Acceptance: acc:define-plans:C001-SMOKE-001-seed
# Acceptance: acc:define-plans:C002-SMOKE-001-seed
# Acceptance: acc:define-plans:E001-SMOKE-001-seed
# Acceptance: acc:define-plans:Y001-SMOKE-001-seed
"""Live SMOKE for `feature:define-plans:atdd-plan-session` (#1209).

Each test drives the real `atdd plan session` CLI via subprocess (run-or-fail,
no skip) and asserts one Intent/Attach/Compose/Ratify lifecycle invariant against the live state
machine in plan_session.py — the canonical `atdd plan` decomposition session.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

_SRC = Path(__file__).resolve().parents[4]
_SPEC = {
    "wagon": "play-audio", "description": "play audio during the commute smoke",
    "subject": "agent:planner", "context": "commute", "action": "plays audio",
    "goal": "music on the go", "outcome": "audio plays",
    "produce": [{"name": "commons:audio:stream"}],
}


def _sess(root, *args):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(root)}
    return subprocess.run([sys.executable, "-m", "atdd", "plan", "--root", str(root), *args],
                          cwd=str(root), env=env, capture_output=True, text=True, timeout=60)


def _state(r):
    assert r.returncode == 0, r.stderr
    return json.loads([ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip().startswith("{")][-1])


def _to_prepare_with_unit(root, sid):
    """Drive a session to the Prepare step carrying one kept-able wagon unit."""
    (root / "plan").mkdir(exist_ok=True)
    _state(_sess(root, "start", "--id", sid, "--main-job", "Listen to music while commuting", "--issue", "my-plan"))
    _sess(root, "advance", "--id", sid, "--step", "attach")
    _sess(root, "source", "--id", sid, "commute spec")
    _sess(root, "advance", "--id", sid, "--step", "compose")
    _sess(root, "unit", "--id", sid, "--kind", "wagon", "--ref", "play-audio", "--spec", json.dumps(_SPEC))


# acc:define-plans:D001-SMOKE-001-seed
def test_d001_define_gate_blocks_advance_without_main_job(tmp_path):
    (tmp_path / "plan").mkdir()
    _state(_sess(tmp_path, "start", "--id", "d1", "--issue", "my-plan"))  # no main-job
    r = _sess(tmp_path, "advance", "--id", "d1", "--step", "attach")
    assert r.returncode != 0, "advance to Locate without a main-job must be refused"
    assert "main job" in (r.stdout + r.stderr).lower()


# acc:define-plans:L001-SMOKE-001-seed
def test_l001_locate_binds_source_to_session_state(tmp_path):
    (tmp_path / "plan").mkdir()
    _state(_sess(tmp_path, "start", "--id", "l1", "--main-job", "job", "--issue", "my-plan"))
    _sess(tmp_path, "advance", "--id", "l1", "--step", "attach")
    _sess(tmp_path, "source", "--id", "l1", "commute spec text")
    st = _state(_sess(tmp_path, "show", "--id", "l1"))  # reload from disk
    assert any("commute spec text" in str(s) for s in st["sources"]), "captured source must persist in session state"


# acc:define-plans:P001-SMOKE-001-seed
def test_p001_prepare_rejects_unit_with_invalid_author_spec(tmp_path):
    (tmp_path / "plan").mkdir()
    _state(_sess(tmp_path, "start", "--id", "p1", "--main-job", "job", "--issue", "my-plan"))
    _sess(tmp_path, "advance", "--id", "p1", "--step", "attach")
    _sess(tmp_path, "source", "--id", "p1", "spec")
    _sess(tmp_path, "advance", "--id", "p1", "--step", "compose")
    r = _sess(tmp_path, "unit", "--id", "p1", "--kind", "wagon", "--ref", "bad", "--spec", "{not-valid-json")
    assert r.returncode != 0, "a unit with a malformed atdd author spec must be rejected"


# acc:define-plans:C001-SMOKE-001-seed
def test_c001_author_refused_before_confirm(tmp_path):
    _to_prepare_with_unit(tmp_path, "c1")
    _sess(tmp_path, "advance", "--id", "c1", "--step", "ratify")
    pre = _sess(tmp_path, "author", "--id", "c1")
    assert pre.returncode != 0, "authoring before Ratify must be refused (confirm-before-author)"
    assert not (tmp_path / "plan" / "play_audio").exists(), "no artifact may be written before confirm"


# acc:define-plans:C002-SMOKE-001-seed
def test_c002_cannot_skip_a_step(tmp_path):
    (tmp_path / "plan").mkdir()
    _state(_sess(tmp_path, "start", "--id", "c2", "--main-job", "job", "--issue", "my-plan"))
    r = _sess(tmp_path, "advance", "--id", "c2", "--step", "compose")  # skip Locate
    assert r.returncode != 0, "a step may not be skipped"
    assert "skip" in (r.stdout + r.stderr).lower()


# acc:define-plans:E001-SMOKE-001-seed
def test_e001_confirm_authors_each_kept_unit(tmp_path):
    _to_prepare_with_unit(tmp_path, "e1")
    _sess(tmp_path, "advance", "--id", "e1", "--step", "ratify")
    _sess(tmp_path, "decide", "--id", "e1", "--ref", "play-audio", "--verdict", "keep")
    _sess(tmp_path, "confirm", "--id", "e1")
    out = _state(_sess(tmp_path, "author", "--id", "e1"))
    assert out["step"] == "authored" and out["authored"], "Confirm must author each kept unit"
    assert (tmp_path / "plan" / "play_audio" / "_play_audio.yaml").exists(), "the kept wagon must be written"


# acc:define-plans:Y001-SMOKE-001-seed
def test_y001_decide_records_verdict_via_elicit(tmp_path):
    _to_prepare_with_unit(tmp_path, "y1")
    _sess(tmp_path, "advance", "--id", "y1", "--step", "ratify")
    st = _state(_sess(tmp_path, "decide", "--id", "y1", "--ref", "play-audio", "--verdict", "keep"))
    assert any(u["ref"] == "play-audio" and u["verdict"] == "keep" for u in st["units"]), "keep/pivot/kill must be recorded"
