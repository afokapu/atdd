# Phase: SMOKE
# Layer: integration
"""Real-life smoke for the coach core convention atomization (#1116, Slice 2 of #1113).

Exercises the actual ``atdd author`` CLI end-to-end (no mocks) and verifies the
committed core coach convention-nodes + the core-to-core coach relationship edges
are schema-valid and referentially coherent — every coach edge endpoint resolves to a
real coach node. Adds the Slice-2 NO-LEAKAGE guard: every authored core coach node
traces to a row classified ``core`` in docs/coach-convention-decomposition-plan.md,
and nothing is authored from an extension/workspace/design_candidate row.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

_SRC = Path(__file__).resolve().parents[4]                      # .../src
_REPO = _SRC.parent
_NODES = _SRC / "atdd" / "coach" / "conventions" / "nodes"
_CORE_GRAPH = _SRC / "atdd" / "coach" / "graph" / "relationships.yaml"
_NODE_SCHEMA = _SRC / "atdd" / "planner" / "schemas" / "author" / "convention-node.schema.json"
_PLAN = _REPO / "docs" / "coach-convention-decomposition-plan.md"


def _cli(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run([sys.executable, "-m", "atdd", "author", *args],
                          cwd=str(cwd), env=env, capture_output=True, text=True, timeout=90)


def _coach_nodes():
    out = []
    for f in sorted(_NODES.glob("coach.*.convention.yaml")):
        out.append((f, yaml.safe_load(f.read_text())))
    return out


def _plan_rows():
    """Parse the machine-actionable `rows:` YAML block from the Slice-1 plan."""
    text = _PLAN.read_text()
    blocks = re.findall(r"```yaml\n(.*?)```", text, re.S)
    rows_block = next(b for b in blocks if b.lstrip().startswith("rows:"))
    return yaml.safe_load(rows_block)["rows"]


def _ids_from(field):
    """Split a `a; b; c` source_rule_id string into individual ids (ignore null)."""
    if not field:
        return []
    return [p.strip() for p in str(field).split(";") if p.strip() and "<" not in p]


def test_real_cli_authors_a_schema_valid_coach_node(tmp_path):
    schema = json.loads(_NODE_SCHEMA.read_text())
    r = _cli(["convention-node", "--core", "--role", "coach",
              "--rule-id", "coach.smoke.demo-rule", "--statement", "A demo coach rule for the smoke.",
              "--rationale", "Proves the real CLI authors a complete coach node.",
              "--term", "demo_term=a term written by the real CLI"], tmp_path)
    assert r.returncode == 0, r.stderr
    node = yaml.safe_load((tmp_path / "src/atdd/coach/conventions/nodes/coach.smoke.demo-rule.convention.yaml").read_text())
    jsonschema.validate(node, schema)
    assert node["rationale"].startswith("Proves")


def test_committed_coach_nodes_and_graph_are_coherent():
    schema = json.loads(_NODE_SCHEMA.read_text())
    node_ids = set()
    nodes = _coach_nodes()
    assert len(nodes) >= 31, f"expected the atomized core coach node set, found {len(nodes)}"
    for f, node in nodes:
        jsonschema.validate(node, schema)                       # every committed node is schema-valid
        assert f.name == f"{node['rule_id']}.convention.yaml"
        assert node["rule_id"].startswith("coach.")
        node_ids.add(node["rule_id"])

    graph = yaml.safe_load(_CORE_GRAPH.read_text())
    assert graph["graph_id"] == "atdd.convention.relationships"
    coach_edges = [e for e in graph["edges"] if e["source_ref"].startswith("coach.") or e["target_ref"].startswith("coach.")]
    assert len(coach_edges) >= 26
    # referential integrity + criterion 7: coach edges are coach-core -> coach-core, both endpoints resolve
    for e in coach_edges:
        for ref in (e["source_ref"], e["target_ref"]):
            rule_id = ref.split("#", 1)[0]
            assert rule_id.startswith("coach."), f"coach edge endpoint {ref!r} is not coach-core"
            assert rule_id in node_ids, f"edge ref {ref!r} points at a missing coach node"


def test_high_fidelity_parity_across_core_coach_conventions():
    """Criteria 3/4/5: every coach node is v1.1.0 with source provenance + parity."""
    schema = json.loads(_NODE_SCHEMA.read_text())
    assert schema["$id"] == "atdd:author:convention-node:1.1.0"
    for f, node in _coach_nodes():
        assert str(node.get("schema_version")) == "1.1.0", f"{f.name} not schema 1.1.0"
        assert node.get("source", {}).get("legacy_path"), f"{f.name} missing source.legacy_path"
        assert node["source"]["legacy_path"].startswith("src/atdd/coach/conventions/"), f"{f.name} bad legacy_path"
        assert node["source"].get("legacy_section"), f"{f.name} missing source.legacy_section"
        assert node["source"].get("extraction_mode") == "high_fidelity", f"{f.name} not high_fidelity"
        assert "parity" in node, f"{f.name} missing parity block"
        # criterion 6: an implementation ref, when present, names a real <module>::<func>
        impl = node.get("implementation")
        if impl:
            assert "::" in impl.get("ref", ""), f"{f.name} implementation.ref not <module>::<func>"


def test_no_non_core_leakage_into_coach_core_nodes():
    """Criterion 9 (the Slice-2 guard): no core coach node derives from an
    extension/workspace/legacy_redirect/design_candidate row. Mechanical join on
    the Slice-1 classification plan via source.legacy_rule_id."""
    if not _PLAN.exists():
        pytest.skip("classification plan not present (non-repo checkout)")
    rows = _plan_rows()
    core_legacy, noncore_legacy = set(), set()
    design_candidates = set()
    core_files = set()
    for r in rows:
        ids = set(_ids_from(r.get("source_rule_id")))
        cls = r["classification"]
        if cls == "core":
            core_legacy |= ids
            core_files.add(str(r["source_file"]))
        else:
            noncore_legacy |= ids
            if cls == "design_candidate" and r.get("candidate_rule_id") and "<" not in str(r["candidate_rule_id"]):
                design_candidates.add(r["candidate_rule_id"])
    # legacy rules that belong ONLY to non-core rows must never back a core node
    exclusive_noncore = noncore_legacy - core_legacy

    for f, node in _coach_nodes():
        rid = node["rule_id"]
        # canary: a design_candidate concept must NOT have been authored as a node
        assert rid not in design_candidates, f"{f.name} authors a design_candidate concept ({rid})"
        legacy_rid = node.get("source", {}).get("legacy_rule_id")
        if legacy_rid:
            assert legacy_rid not in exclusive_noncore, (
                f"{f.name} derives from {legacy_rid!r} which is classified non-core only")
        # criterion 1: every node traces to a core row
        legacy_file = Path(node["source"]["legacy_path"]).name
        traces = (
            (legacy_rid and legacy_rid in core_legacy)
            or rid.startswith("coach.rule-id.")          # bundled rule-id core row (placeholder candidate)
            or legacy_file in core_files
        )
        assert traces, f"{f.name} does not trace to any core-classified row"


def _find_legacy_rule(obj, rid):
    if isinstance(obj, dict):
        if obj.get("id") == rid:
            return obj
        for v in obj.values():
            r = _find_legacy_rule(v, rid)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_legacy_rule(v, rid)
            if r:
                return r
    return None


def test_nodes_do_not_drop_source_fix_hints():
    """#1124 parity-depth guard: a node whose source legacy rule carries a `fix_hint`
    MUST carry it in `content.fix_hint` (operational long-form not compressed away),
    and `parity.fix_hint_preserved` MUST be honest (true iff content.fix_hint present).
    Scans the planner + coach node sets. This is the guard whose absence let the
    #1110/#1116 atomizations drop fix_hints/exceptions silently."""
    node_dirs = [_SRC / "atdd" / "planner" / "conventions" / "nodes", _NODES]
    dropped, lies = [], []
    for nd in node_dirs:
        for f in sorted(nd.glob("*.convention.yaml")):
            n = yaml.safe_load(f.read_text())
            content = n.get("content") or {}
            parity = n.get("parity") or {}
            if bool(parity.get("fix_hint_preserved")) != bool(content.get("fix_hint")):
                lies.append(f"{f.name}: fix_hint_preserved={parity.get('fix_hint_preserved')} "
                            f"but content.fix_hint {'present' if content.get('fix_hint') else 'absent'}")
            src = n.get("source") or {}
            lp, lr = src.get("legacy_path"), src.get("legacy_rule_id")
            if lp and lr and (_REPO / lp).exists():
                rule = _find_legacy_rule(yaml.safe_load((_REPO / lp).read_text()), lr)
                if rule and rule.get("fix_hint") and not content.get("fix_hint"):
                    dropped.append(f.name)
    assert not dropped, f"nodes dropped a source fix_hint instead of carrying it: {dropped}"
    assert not lies, f"parity.fix_hint_preserved inconsistent with content.fix_hint: {lies}"
