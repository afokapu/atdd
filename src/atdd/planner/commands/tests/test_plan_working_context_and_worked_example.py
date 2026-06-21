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
    PlanSession, SessionGateError, Step, Unit, Verdict, build_author_fn,
)

_REPO = Path(__file__).resolve().parents[5]
_SRC = Path(__file__).resolve().parents[4]
_SCHEMAS = _SRC / "atdd" / "planner" / "schemas"


def _schema(kind):
    return json.loads((_SCHEMAS / f"{kind}.schema.json").read_text())


def _op_resolver(choice):
    from atdd.runtime.elicit import (ElicitResponse, ElicitStatus, ElicitRole, Participant, InlineClaudeElicitAdapter)
    return InlineClaudeElicitAdapter(lambda r: ElicitResponse(elicit_id=r.elicit_id, status=ElicitStatus.RESOLVED, resolved_by=Participant(ElicitRole.OPERATOR, "user"), selections=[choice]))


def _pivot_resolver(mod):
    from atdd.runtime.elicit import (ElicitResponse, ElicitStatus, ElicitRole, Participant, InlineClaudeElicitAdapter)
    return InlineClaudeElicitAdapter(lambda r: ElicitResponse(elicit_id=r.elicit_id, status=ElicitStatus.RESOLVED, resolved_by=Participant(ElicitRole.OPERATOR, "user"), selections=["pivot"], freeform=mod))


def test_working_context_includes_session_protocol_nodes_and_edges():
    ctx = load_working_context(_REPO)
    g = ctx["guidelines"]
    for rid in ("planner.plan.session-lifecycle", "planner.plan.confirm-before-author",
                "planner.plan.confirm-binds-an-issue"):
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
    s = PlanSession("worked", main_job="Listen to music while commuting", issue_ref="my-plan")
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


def test_full_decomposition_all_five_kinds_with_keep_pivot_kill(tmp_path):
    """Comprehensive: a session that authors ALL FIVE plan kinds
    (wagon/feature/wmbt/train/acceptance) and exercises keep + pivot + kill."""
    (tmp_path / "plan" / "_trains").mkdir(parents=True)
    (tmp_path / "plan" / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")
    s = PlanSession("full", main_job="Listen to music while commuting", issue_ref="my-plan")
    s.advance(Step.LOCATE); s.sources.append({"type": "text", "value": "spec"})
    s.advance(Step.PREPARE)
    s.add_unit(Unit(kind="wagon", ref="full-demo", spec={
        "wagon": "full-demo", "description": "the full demo wagon for all-kinds coverage",
        "subject": "agent:planner", "context": "commute", "action": "does it",
        "goal": "cover all kinds", "outcome": "all authored", "produce": [{"name": "commons:demo:thing"}]}))
    s.add_unit(Unit(kind="feature", ref="do-it", spec={
        "urn": "feature:full-demo:do-it", "wagon": "wagon:full-demo",
        "description": "the do-it feature covering the wmbt end to end",
        "sizing": {"wmbts": 1, "footprint_score": 4, "footprint_size": "S"},
        "wmbts": ["wmbt:full-demo:E001"],
        "components": {"backend": {"application": [{"type": "use_cases", "count": 1, "rationale": "the do-it path"}]}}}))
    s.add_unit(Unit(kind="wmbt", ref="E001", spec={
        "wagon_slug": "full-demo", "code": "E001", "step": "execute", "direction": "maximize",
        "dimension": "likelihood", "object_of_control": "thing-creation",
        "context_clarifier": "when doing it the thing is created without error",
        "lens": "functional.effectiveness",
        "statement": "maximize likelihood of thing-creation when doing it"}))
    s.add_unit(Unit(kind="train", ref="0009-full-demo", spec={
        "train_id": "0009-full-demo", "wagons": ["full-demo"], "description": "the full demo train"}))
    s.add_unit(Unit(kind="acceptance", ref="extra-acc", spec={
        "wmbt_urn": "wmbt:full-demo:E001",
        "block": {"identity": {"urn": "acc:full-demo:E001-UNIT-002-extra", "id": "AC-UNIT-002",
                               "purpose": "an appended acceptance", "phase": "GREEN"},
                  "harness": {"type": "unit", "category": "backend"},
                  "given": {"abstract": ["a"]}, "when": {"abstract": "b"}, "then": {"abstract": ["c"]}}}))
    s.add_unit(Unit(kind="wagon", ref="kill-me", spec={"wagon": "kill-me"}))
    s.add_unit(Unit(kind="wagon", ref="pivot-me", spec={"wagon": "pivot-me"}))
    s.advance(Step.CONFIRM)

    keep = _op_resolver("keep")
    for ref in ("full-demo", "do-it", "E001", "0009-full-demo", "extra-acc"):
        s.decide(ref, keep)
    s.decide("kill-me", _op_resolver("kill"))
    s.decide("pivot-me", _pivot_resolver("drop audio; focus on podcasts"))

    # pivot records its modification and is NON-TERMINAL — confirm refuses it
    pm = s._unit("pivot-me")
    assert pm["verdict"] == Verdict.PIVOT.value and pm["modification"] == "drop audio; focus on podcasts"
    import pytest as _pytest
    with _pytest.raises(SessionGateError):
        s.confirm()
    # operator re-resolves the pivot (re-drafted, then kept or killed) — here: kill
    s.decide("pivot-me", _op_resolver("kill"))
    assert {u["ref"] for u in s.kept_units()} == {"full-demo", "do-it", "E001", "0009-full-demo", "extra-acc"}

    s.confirm()
    s.author(build_author_fn(tmp_path))

    base = tmp_path / "plan" / "full_demo"
    validate(yaml.safe_load((base / "_full_demo.yaml").read_text()), _schema("wagon"))
    validate(yaml.safe_load((base / "features" / "do_it.yaml").read_text()), _schema("feature"))
    wmbt = yaml.safe_load((base / "E001.yaml").read_text())
    assert "SMOKE" in [a["identity"]["phase"] for a in wmbt["acceptances"]]            # wmbt + seeded smoke
    assert "acc:full-demo:E001-UNIT-002-extra" in [a["identity"]["urn"] for a in wmbt["acceptances"]]  # acceptance appended
    assert (tmp_path / "plan" / "_trains" / "0009-full-demo.yaml").exists()            # train
    assert "0009-full-demo" in (tmp_path / "plan" / "_trains.yaml").read_text()
    assert not (tmp_path / "plan" / "kill_me").exists()                                 # killed: not authored
    assert not (tmp_path / "plan" / "pivot_me").exists()                                # pivoted (not keep): not authored
