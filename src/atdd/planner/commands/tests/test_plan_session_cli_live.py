# URN: test:atdd-plan-core:session-cli:full-session-live
# Issue: #1139
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""#1139 slice 4 — live end-to-end smoke of the `atdd plan session` CLI.

Drives a full gated session via subprocess against the real CLI (run-or-fail,
no skip): start -> D/L/P/C -> keep -> confirm -> author. Asserts the on-Confirm
boundary really invokes the #1144 writer and produces a schema-valid wagon, and
that confirm-before-author is enforced (authoring before confirm is refused).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import validate

_SRC = Path(__file__).resolve().parents[4]
_WAGON_SCHEMA = json.loads((_SRC / "atdd" / "planner" / "schemas" / "wagon.schema.json").read_text())
_SPEC = {
    "wagon": "play-audio", "description": "play audio during the commute live smoke",
    "subject": "agent:planner", "context": "commute", "action": "plays audio",
    "goal": "music on the go", "outcome": "audio plays",
    "produce": [{"name": "commons:audio:stream"}],
}


def _sess(root, *args):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(root)}
    return subprocess.run([sys.executable, "-m", "atdd", "plan", "session", "--root", str(root), *args],
                          cwd=str(root), env=env, capture_output=True, text=True, timeout=60)


def _state(r):
    assert r.returncode == 0, r.stderr
    return json.loads([ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip().startswith("{")][-1])


def test_full_session_authors_valid_wagon_via_cli(tmp_path):
    (tmp_path / "plan").mkdir()
    assert _state(_sess(tmp_path, "start", "--id", "s1", "--main-job", "Listen to music while commuting"))["step"] == "define"
    _sess(tmp_path, "advance", "--id", "s1", "--step", "locate")
    _sess(tmp_path, "source", "--id", "s1", "commute spec")
    _sess(tmp_path, "advance", "--id", "s1", "--step", "prepare")
    _sess(tmp_path, "unit", "--id", "s1", "--kind", "wagon", "--ref", "play-audio", "--spec", json.dumps(_SPEC))
    _sess(tmp_path, "advance", "--id", "s1", "--step", "confirm")

    # confirm-before-author: authoring before confirm must be refused
    pre = _sess(tmp_path, "author", "--id", "s1")
    assert pre.returncode != 0, "author before confirm must fail"
    assert not (tmp_path / "plan" / "play_audio").exists()

    assert _state(_sess(tmp_path, "decide", "--id", "s1", "--ref", "play-audio", "--verdict", "keep"))["units"][0]["verdict"] == "keep"
    _sess(tmp_path, "confirm", "--id", "s1")
    out = _state(_sess(tmp_path, "author", "--id", "s1"))
    assert out["step"] == "authored"
    assert out["authored"], "author should report written paths"

    wagon = tmp_path / "plan" / "play_audio" / "_play_audio.yaml"
    assert wagon.exists()
    validate(yaml.safe_load(wagon.read_text()), _WAGON_SCHEMA)
