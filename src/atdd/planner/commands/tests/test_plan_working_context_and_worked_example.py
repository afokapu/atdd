# URN: test:atdd-plan-core:working-context:assembly-and-worked-example
# Issue: #1139 (slice 6; worked example replaces #766)
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""#1139 slice 6 — working-context assembly + an end-to-end worked example.

(1) load_working_context assembles the agent's guidelines from the
    session-protocol (and, once #761 lands, decomposition-protocol) nodes + the
    flow edges among them; the `guidelines` CLI op emits it.
(2) A worked example drives a full session that authors MULTIPLE kinds
    (wagon + feature + wmbt) via the real #1144 writers and validates each.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import validate

from atdd.planner.commands.plan_context import load_working_context
from atdd.planner.commands.plan_session import (
    PlanSession, Step, Unit, Verdict, build_author_fn,
)

_REPO = Path(__file__).resolve().parents[5]
_SRC = Path(__file__).resolve().parents[4]
_SCHEMAS = _SRC / "atdd" / "planner" / "schemas"


def _schema(kind):
    return json.loads((_SCHEMAS / f"{kind}.schema.json").read_text())


def test_working_context_includes_session_protocol_nodes_and_edges():
    ctx = load_working_context(_REPO)
    g = ctx["guidelines"]
    for rid in ("planner.plan.session-lifecycle", "planner.plan.confirm-before-author",
                "planner.plan.in-session-no-issue"):
        assert rid in g, f"{rid} missing from working context"
        assert g[rid]["statement"]
    # the protocol-flow edge between the plan nodes is surfaced
    assert any(e["source"].startswith("planner.plan.") and e["target"].startswith("planner.plan.")
               for e in ctx["edges"])


def test_guidelines_cli_emits_context():
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(_REPO)}
    r = subprocess.run([sys.executable, "-m", "atdd", "plan", "session", "--root", str(_REPO), "guidelines"],
                       cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    doc = json.loads([ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip().startswith("{")][-1])
    assert "planner.plan.session-lifecycle" in doc["guidelines"]


def test_worked_example_authors_wagon_feature_and_wmbt(tmp_path):
    (tmp_path / "plan").mkdir()
    s = PlanSession("worked", main_job="Listen to music while commuting")
    s.advance(Step.LOCATE); s.sources.append({"type": "text", "value": "music app spec"})
    s.advance(Step.PREPARE)
    s.add_unit(Unit(kind="wagon", ref="stream-audio", spec={
        "wagon": "stream-audio", "description": "stream audio to the commuter",
        "subject": "agent:planner", "context": "commute", "action": "streams audio",
        "goal": "music on the go", "outcome": "audio streams", "produce": [{"name": "commons:audio:stream"}]}))
    s.add_unit(Unit(kind="feature", ref="play-track", spec={
        "urn": "feature:stream-audio:play-track", "wagon": "wagon:stream-audio",
        "description": "play a selected track end to end for the commuter",
        "sizing": {"wmbts": 1, "footprint_score": 4, "footprint_size": "S"},
        "wmbts": ["wmbt:stream-audio:E001"],
        "components": {"backend": {"application": [{"type": "use_cases", "count": 1, "rationale": "the play-track path"}]}}}))
    s.add_unit(Unit(kind="wmbt", ref="E001", spec={
        "wagon_slug": "stream-audio", "code": "E001", "step": "execute", "direction": "maximize",
        "dimension": "likelihood", "object_of_control": "track-playback",
        "context_clarifier": "when a track is selected it plays without buffering stalls",
        "lens": "functional.effectiveness",
        "statement": "maximize likelihood of track-playback when a commuter selects a track"}))
    s.advance(Step.CONFIRM)
    for ref in ("stream-audio", "play-track", "E001"):
        s.units[[u["ref"] for u in s.units].index(ref)]["verdict"] = Verdict.KEEP.value
    s.confirm()
    s.author(build_author_fn(tmp_path))

    base = tmp_path / "plan" / "stream_audio"
    validate(yaml.safe_load((base / "_stream_audio.yaml").read_text()), _schema("wagon"))
    validate(yaml.safe_load((base / "features" / "play_track.yaml").read_text()), _schema("feature"))
    wmbt = yaml.safe_load((base / "E001.yaml").read_text())
    assert "SMOKE" in [a["identity"]["phase"] for a in wmbt["acceptances"]]  # create_wmbt seeded it
