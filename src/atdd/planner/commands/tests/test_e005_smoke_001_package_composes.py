# URN: test:author-atdd-substrate:package-composition:E005-SMOKE-001-package-composes
# Acceptance: acc:author-atdd-substrate:E005-SMOKE-001-package-composes
# WMBT: wmbt:author-atdd-substrate:E005
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E005-SMOKE-001 — a real installed package set discovers, validates by kind, keeps
its source graph separate from core, and composes into a protocol view with derived
realization edges. Runs against the fixture (always) and atdd-extensions/official
(skip-if-absent)."""
from __future__ import annotations

import json
import pathlib

import jsonschema
import pytest
import yaml

from atdd.planner.commands import compose as C

_SRC = pathlib.Path(__file__).resolve().parents[4]
_REPO = _SRC.parent
_FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "packages"
_NODE_SCHEMA = json.loads(
    (_SRC / "atdd" / "planner" / "schemas" / "author" / "convention-node.schema.json").read_text()
)
_CORE_GRAPH_ID = "atdd.convention.relationships"


def _assert_composes(root):
    core = C.installed_core_node_ids()
    pkgs = C.discover_packages(root)
    exts = [p for p in pkgs if p["kind"] == "extension"]
    wss = [p for p in pkgs if p["kind"] == "workspace"]
    assert exts and wss, f"discover an extension + workspace under {root}"
    for p in pkgs:
        C.validate_by_kind(p)                                        # validate by kind
    for ext in exts:
        m = ext["manifest"]
        for rel in (m.get("owns") or {}).get("conventions", []):
            jsonschema.validate(yaml.safe_load((ext["dir"] / rel).read_text()), _NODE_SCHEMA)
        gp = ext["dir"] / "relationships.yaml"
        if gp.exists():
            gid = (yaml.safe_load(gp.read_text()) or {}).get("graph_id")
            assert gid and gid != _CORE_GRAPH_ID and gid.startswith(m["extension_id"])  # separate graph
        C.validate_realizes(ext, core)
        view = C.compose_protocol_view(core, ext, mode="composed")
        assert not view["targets_unresolved"]
        assert view["executed_implementations"] == []
    return exts


def test_fixture_package_set_composes():
    exts = _assert_composes(_FIX)
    assert any(e["manifest"]["extension_id"] == "acme.extension.demo" for e in exts)


def test_official_packages_compose_if_present():
    candidates = [_REPO.parent.parent / "atdd-extensions" / "official",
                  _REPO.parent / "atdd-extensions" / "official"]
    official = next((c for c in candidates if c.exists()), None)
    if official is None:
        pytest.skip("atdd-extensions/official not checked out beside core")
    exts = _assert_composes(official)
    assert any(e["manifest"]["extension_id"] == "atdd.extension.github" for e in exts)
