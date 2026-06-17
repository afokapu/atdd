# Phase: SMOKE
# Layer: integration
"""Package discovery + composition smoke (#1130).

Proves ATDD can DISCOVER + COMPOSE installed extension/workspace packages into a
protocol view WITHOUT executing any runtime implementation. Ten criteria, run against a
CI-portable fixture package set (always) and the real `atdd-extensions/official`
packages when that repo is checked out beside core (skip-if-absent — covers
`atdd.extension.github` literally).
"""
from __future__ import annotations

import json
import pathlib

import jsonschema
import pytest
import yaml

from atdd.planner.commands import compose as C
from atdd.planner.commands.author_manifest import extension_targets_satisfied_by

_SRC = pathlib.Path(__file__).resolve().parents[4]            # .../src
_REPO = _SRC.parent
_FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "packages"
_CORE_NODES = _SRC / "atdd" / "coach" / "conventions" / "nodes"
_PLANNER_NODES = _SRC / "atdd" / "planner" / "conventions" / "nodes"
_NODE_SCHEMA = json.loads(
    (_SRC / "atdd" / "planner" / "schemas" / "author" / "convention-node.schema.json").read_text()
)
_CORE_GRAPH_ID = "atdd.convention.relationships"


def _core_node_ids() -> set[str]:
    ids = set()
    for d in (_CORE_NODES, _PLANNER_NODES):
        for f in d.glob("*.convention.yaml"):
            rid = (yaml.safe_load(f.read_text()) or {}).get("rule_id")
            if rid:
                ids.add(rid)
    return ids


def _assert_all_criteria(root: pathlib.Path, core_ids: set[str]) -> list[dict]:
    pkgs = C.discover_packages(root)
    exts = [p for p in pkgs if p["kind"] == "extension"]
    wss = [p for p in pkgs if p["kind"] == "workspace"]
    # (1) discover installed extension + workspace packages
    assert exts, f"no extension package discovered under {root}"
    assert wss, f"no workspace package discovered under {root}"
    ws_by_id = {w["manifest"].get("workspace_id"): w["manifest"] for w in wss}

    for p in pkgs:
        assert p["manifest"], f"(2) empty manifest at {p['manifest_path']}"   # (2) read manifests
        C.validate_by_kind(p)                                                  # (3) validate by kind

    for ext in exts:
        d, m = ext["dir"], ext["manifest"]
        owns = (m.get("owns") or {}).get("conventions") or []
        assert owns, f"{m.get('extension_id')} owns no conventions"
        for rel in owns:
            assert (d / rel).exists(), f"(4) owns path missing: {rel}"        # (4) owns paths exist
            node = yaml.safe_load((d / rel).read_text())
            jsonschema.validate(node, _NODE_SCHEMA)                            # (5) nodes validate

        gp = d / "relationships.yaml"                                         # (6) graphs load
        if gp.exists():
            g = yaml.safe_load(gp.read_text()) or {}
            assert g.get("graph_id"), f"(6) {gp} missing graph_id"
            assert g["graph_id"] != _CORE_GRAPH_ID, "(7) extension graph must stay separate from core"
            assert g["graph_id"].startswith(m["extension_id"]), "(7) extension graph_id must be ext-namespaced"

        view = C.compose_protocol_view(core_ids, ext)
        # (8) depends_on.targets resolves only real core nodes
        assert not view["targets_unresolved"], f"(8) unresolved targets: {view['targets_unresolved']}"
        assert view["targets_resolved"], "(8) extension declares ≥1 resolvable core target"
        # (9) design_candidates are non-normative: never appear as hard targets
        for dc in view["design_candidates"]:
            assert dc not in C.extension_target_nodes(m), f"(9) design_candidate {dc} leaked into targets"
        # (10) composes into a protocol view WITHOUT executing runtime
        assert view["executed_implementations"] == [], "(10) composition must not execute runtime"
        assert view["contributes"], "(10) composition surfaces the extension's contributed nodes"

        # bonus: declared workspace contract is satisfied by a present provider
        for entry in ((m.get("depends_on") or {}).get("workspaces") or []):
            prov = ws_by_id.get(entry.get("id"))
            if prov is not None:
                assert extension_targets_satisfied_by(m, prov), (
                    f"workspace contract {entry} not satisfied by {prov.get('workspace_id')}"
                )
    return exts


def test_fixture_packages_compose():
    """CI-portable: the fixture extension + workspace satisfy all 10 criteria."""
    exts = _assert_all_criteria(_FIXTURES, _core_node_ids())
    assert any(e["manifest"]["extension_id"] == "acme.extension.demo" for e in exts)


def test_real_atdd_extensions_compose_if_present():
    """#10 literally: the real `atdd.extension.github` composes. Skips when the
    `atdd-extensions` repo is not checked out beside core (e.g. in core CI)."""
    candidates = [
        _REPO.parent.parent / "atdd-extensions" / "official",
        _REPO.parent / "atdd-extensions" / "official",
    ]
    official = next((c for c in candidates if c.exists()), None)
    if official is None:
        pytest.skip("atdd-extensions/official not checked out beside core")
    exts = _assert_all_criteria(official, _core_node_ids())
    assert any(e["manifest"]["extension_id"] == "atdd.extension.github" for e in exts), \
        "expected atdd.extension.github among discovered official packages"
