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
    assert _state(_sess(tmp_path, "start", "--id", "s1", "--main-job", "Listen to music while commuting", "--issue", "my-plan"))["step"] == "define"
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


_FEATURE_SCHEMA = json.loads((_SRC / "atdd" / "planner" / "schemas" / "feature.schema.json").read_text())


def test_full_decomposition_all_five_kinds_keep_pivot_kill_via_cli(tmp_path):
    """Comprehensive CLI smoke: drive ALL FIVE plan kinds + keep/pivot/kill through
    `atdd plan session` subprocesses, matching the in-process worked example."""
    (tmp_path / "plan" / "_trains").mkdir(parents=True)
    (tmp_path / "plan" / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")

    def U(kind, ref, spec):
        assert _sess(tmp_path, "unit", "--id", "f", "--kind", kind, "--ref", ref, "--spec", json.dumps(spec)).returncode == 0

    _state(_sess(tmp_path, "start", "--id", "f", "--main-job", "Listen to music while commuting", "--issue", "my-plan"))
    _sess(tmp_path, "advance", "--id", "f", "--step", "locate"); _sess(tmp_path, "source", "--id", "f", "spec")
    _sess(tmp_path, "advance", "--id", "f", "--step", "prepare")
    U("wagon", "full-demo", {"wagon": "full-demo", "description": "the full demo wagon all kinds",
        "subject": "agent:planner", "context": "commute", "action": "does it", "goal": "cover all kinds",
        "outcome": "all authored", "produce": [{"name": "commons:demo:thing"}]})
    U("feature", "do-it", {"urn": "feature:full-demo:do-it", "wagon": "wagon:full-demo",
        "description": "the do-it feature covering the wmbt end to end",
        "sizing": {"wmbts": 1, "footprint_score": 4, "footprint_size": "S"}, "wmbts": ["wmbt:full-demo:E001"],
        "components": {"backend": {"application": [{"type": "use_cases", "count": 1, "rationale": "the do-it path"}]}}})
    U("wmbt", "E001", {"wagon_slug": "full-demo", "code": "E001", "step": "execute", "direction": "maximize",
        "dimension": "likelihood", "object_of_control": "thing-creation",
        "context_clarifier": "when doing it the thing is created without error",
        "lens": "functional.effectiveness", "statement": "maximize likelihood of thing-creation when doing it"})
    U("train", "0009-full-demo", {"train_id": "0009-full-demo", "wagons": ["full-demo"], "description": "the full demo train"})
    U("acceptance", "extra-acc", {"wmbt_urn": "wmbt:full-demo:E001",
        "block": {"identity": {"urn": "acc:full-demo:E001-UNIT-002-extra", "id": "AC-UNIT-002",
                               "purpose": "an appended acceptance", "phase": "GREEN"},
                  "harness": {"type": "unit", "category": "backend"},
                  "given": {"abstract": ["a"]}, "when": {"abstract": "b"}, "then": {"abstract": ["c"]}}})
    U("wagon", "kill-me", {"wagon": "kill-me"})
    U("wagon", "pivot-me", {"wagon": "pivot-me"})
    _sess(tmp_path, "advance", "--id", "f", "--step", "confirm")

    for ref in ("full-demo", "do-it", "E001", "0009-full-demo", "extra-acc"):
        _sess(tmp_path, "decide", "--id", "f", "--ref", ref, "--verdict", "keep")
    _sess(tmp_path, "decide", "--id", "f", "--ref", "kill-me", "--verdict", "kill")
    _sess(tmp_path, "decide", "--id", "f", "--ref", "pivot-me", "--verdict", "pivot", "--mod", "drop audio")

    # confirm refuses while the pivot is unresolved
    assert _sess(tmp_path, "confirm", "--id", "f").returncode != 0
    _sess(tmp_path, "decide", "--id", "f", "--ref", "pivot-me", "--verdict", "kill")  # re-resolve
    assert _sess(tmp_path, "confirm", "--id", "f").returncode == 0
    out = _state(_sess(tmp_path, "author", "--id", "f"))
    assert out["step"] == "authored" and len(out["authored"]) == 5

    base = tmp_path / "plan" / "full_demo"
    validate(yaml.safe_load((base / "_full_demo.yaml").read_text()), _WAGON_SCHEMA)
    validate(yaml.safe_load((base / "features" / "do_it.yaml").read_text()), _FEATURE_SCHEMA)
    wmbt = yaml.safe_load((base / "E001.yaml").read_text())
    urns = [a["identity"]["urn"] for a in wmbt["acceptances"]]
    assert any(a["identity"]["phase"] == "SMOKE" for a in wmbt["acceptances"])     # seeded smoke
    assert "acc:full-demo:E001-UNIT-002-extra" in urns                            # appended acceptance
    assert (tmp_path / "plan" / "_trains" / "0009-full-demo.yaml").exists()        # train
    assert "0009-full-demo" in (tmp_path / "plan" / "_trains.yaml").read_text()
    assert not (tmp_path / "plan" / "kill_me").exists()                            # killed
    assert not (tmp_path / "plan" / "pivot_me").exists()                           # pivoted->killed
