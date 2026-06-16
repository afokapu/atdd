# Phase: SMOKE
# Layer: integration
"""Real-life smoke for the planner convention atomization (#1107).

Exercises the actual ``atdd author`` CLI end-to-end (no mocks) and verifies the
committed atomization artifacts — the 23 planner convention-nodes and the
13-edge core relationship graph — are schema-valid and referentially coherent:
every edge endpoint resolves to a real node. Also proves core and extension
relationship graphs receive distinct graph_ids.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import jsonschema
import yaml

_SRC = Path(__file__).resolve().parents[4]                      # .../src
_NODES = _SRC / "atdd" / "planner" / "conventions" / "nodes"
_CORE_GRAPH = _SRC / "atdd" / "coach" / "graph" / "relationships.yaml"
_NODE_SCHEMA = _SRC / "atdd" / "planner" / "schemas" / "author" / "convention-node.schema.json"


def _cli(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run([sys.executable, "-m", "atdd", "author", *args],
                          cwd=str(cwd), env=env, capture_output=True, text=True, timeout=90)


def test_real_cli_authors_a_schema_valid_node(tmp_path):
    import json
    schema = json.loads(_NODE_SCHEMA.read_text())
    r = _cli(["convention-node", "--core", "--role", "planner",
              "--rule-id", "planner.smoke.demo-rule", "--statement", "A demo rule for the smoke.",
              "--rationale", "Proves the real CLI authors a complete node.",
              "--term", "demo_term=a term written by the real CLI"], tmp_path)
    assert r.returncode == 0, r.stderr
    node = yaml.safe_load((tmp_path / "src/atdd/planner/conventions/nodes/planner.smoke.demo-rule.convention.yaml").read_text())
    jsonschema.validate(node, schema)        # real schema, real file
    assert node["rationale"].startswith("Proves")


def test_real_cli_core_and_extension_graphs_get_distinct_ids(tmp_path):
    core = _cli(["relationship", "--core", "--source", "planner.smoke.demo-rule",
                 "--type", "requires", "--target", "planner.acceptance.complete",
                 "--foundation", "finish_to_start", "--constraint", "mandatory",
                 "--control", "internal", "--strength", "important", "--reason", "smoke"], tmp_path)
    assert core.returncode == 0, core.stderr
    ext = _cli(["relationship", "--extension", "acme.extension.demo",
                "--source", "coder.source.a", "--type", "requires", "--target", "coder.source.b",
                "--reason", "smoke"], tmp_path)
    assert ext.returncode == 0, ext.stderr
    core_doc = yaml.safe_load((tmp_path / "src/atdd/coach/graph/relationships.yaml").read_text())
    ext_doc = yaml.safe_load((tmp_path / "extensions/acme.extension.demo/relationships.yaml").read_text())
    assert core_doc["graph_id"] == "atdd.convention.relationships"
    assert ext_doc["graph_id"] == "acme.extension.demo.relationships"


def test_committed_nodes_and_graph_are_coherent():
    import json
    schema = json.loads(_NODE_SCHEMA.read_text())
    node_ids = set()
    node_files = sorted(_NODES.glob("planner.*.convention.yaml"))
    assert len(node_files) == 23, f"expected 23 atomized nodes, found {len(node_files)}"
    for f in node_files:
        node = yaml.safe_load(f.read_text())
        jsonschema.validate(node, schema)                # every committed node is schema-valid
        assert f.name == f"{node['rule_id']}.convention.yaml"
        node_ids.add(node["rule_id"])

    graph = yaml.safe_load(_CORE_GRAPH.read_text())
    assert graph["graph_id"] == "atdd.convention.relationships"
    edges = graph["edges"]
    assert len(edges) == 13
    # referential integrity: every edge endpoint (minus a #term suffix) is a real node
    for e in edges:
        for ref in (e["source_ref"], e["target_ref"]):
            rule_id = ref.split("#", 1)[0]
            assert rule_id in node_ids, f"edge ref {ref!r} points at a missing node"
