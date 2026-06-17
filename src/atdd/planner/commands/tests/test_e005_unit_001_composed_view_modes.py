# URN: test:author-atdd-substrate:package-composition:E005-UNIT-001-composed-view-modes
# Acceptance: acc:author-atdd-substrate:E005-UNIT-001-composed-view-modes
# WMBT: wmbt:author-atdd-substrate:E005
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E005-UNIT-001 — compose_protocol_view yields no derived edges in core mode and, in
composed mode, materializes each realizes mapping as a derived edge with the provenance
triple and a core_node→[extension nodes] reverse index, never executing runtime."""
from __future__ import annotations

import pathlib

import yaml

from atdd.planner.commands import compose as C

_DEMO = pathlib.Path(__file__).resolve().parent / "fixtures" / "packages" / "acme.extension.demo"


def _ext():
    return {"kind": "extension", "dir": _DEMO, "manifest_path": _DEMO / "atdd.extension.yaml",
            "manifest": yaml.safe_load((_DEMO / "atdd.extension.yaml").read_text())}


def test_core_mode_is_source_only():
    view = C.compose_protocol_view(C.installed_core_node_ids(), _ext(), mode="core")
    assert view["derived_edges"] == [], "core mode produces no derived edges"
    assert view["executed_implementations"] == []


def test_composed_mode_materializes_derived_edges_with_provenance():
    core = C.installed_core_node_ids()
    ext = _ext()
    view = C.compose_protocol_view(core, ext, mode="composed")
    mappings = C.realizes_mappings(ext["manifest"])
    assert view["derived_edges"], "composed mode materializes realizes -> derived edges"
    assert len(view["derived_edges"]) == len([m for m in mappings if m[1] in core])
    for e in view["derived_edges"]:
        assert e["derived"] is True and e["relation"] == "realizes"
        prov = e["provenance"]
        assert prov["core_authority"] in core
        assert prov["extension_realization"] in view["contributes"]
        assert "execution_target" in prov           # workspace execution target (may be declared)
    # reverse index: core_node -> [extension nodes]
    for cn, ens in view["realization_index"].items():
        assert cn in core and ens
    assert view["executed_implementations"] == [], "composition never runs runtime"


def test_targets_resolve_and_design_candidates_not_realized():
    view = C.compose_protocol_view(C.installed_core_node_ids(), _ext(), mode="composed")
    assert not view["targets_unresolved"]
    for dc in view["design_candidates"]:
        assert dc not in view["realization_index"], "a design_candidate is never realized"
