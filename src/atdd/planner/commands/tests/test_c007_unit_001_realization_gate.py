# URN: test:author-atdd-substrate:package-composition:C007-UNIT-001-realization-gate
# Acceptance: acc:author-atdd-substrate:C007-UNIT-001-realization-gate
# WMBT: wmbt:author-atdd-substrate:C007
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C007-UNIT-001 — the realization gate accepts a well-formed realizes block and
refuses an unresolved core_node, a realized design_candidate, an unowned
extension_node, and an authored cross-package graph edge."""
from __future__ import annotations

import pathlib
import shutil

import pytest
import yaml

from atdd.planner.commands import compose as C

_FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "packages"
_DEMO = _FIX / "acme.extension.demo"


def _core_ids() -> set[str]:
    return C.installed_core_node_ids()


def _temp_ext(tmp_path, mutate):
    dst = tmp_path / "acme.extension.demo"
    shutil.copytree(_DEMO, dst)
    mf = dst / "atdd.extension.yaml"
    data = yaml.safe_load(mf.read_text())
    mutate(data, dst)
    mf.write_text(yaml.safe_dump(data, sort_keys=False))
    return {"kind": "extension", "dir": dst, "manifest_path": mf, "manifest": data}


def test_well_formed_realizes_is_accepted():
    ext = {"kind": "extension", "dir": _DEMO, "manifest_path": _DEMO / "atdd.extension.yaml",
           "manifest": yaml.safe_load((_DEMO / "atdd.extension.yaml").read_text())}
    realized = C.validate_realizes(ext, _core_ids())
    assert realized, "a well-formed realizes block resolves to a realized core node set"
    assert realized <= _core_ids()


def test_unresolved_core_node_is_refused(tmp_path):
    def m(data, _d):
        data["realizes"].append({"extension_node": "demo.area.sample-rule",
                                 "core_node": "coach.bogus.does-not-exist"})
    with pytest.raises(C.CompositionError, match="does not resolve to a shipped core node"):
        C.validate_realizes(_temp_ext(tmp_path, m), _core_ids())


def test_realizing_a_design_candidate_is_refused(tmp_path):
    def m(data, _d):
        data["realizes"].append({"extension_node": "demo.area.sample-rule",
                                 "core_node": "coach.execution.work-provenance"})
    with pytest.raises(C.CompositionError, match="design_candidate .* cannot be realized"):
        C.validate_realizes(_temp_ext(tmp_path, m), _core_ids())


def test_unowned_extension_node_is_refused(tmp_path):
    def m(data, _d):
        data["realizes"].append({"extension_node": "github.not.owned-here",
                                 "core_node": "coach.lifecycle.phase-machine"})
    with pytest.raises(C.CompositionError, match="not owned by this extension"):
        C.validate_realizes(_temp_ext(tmp_path, m), _core_ids())


def test_authored_cross_package_edge_is_refused(tmp_path):
    def m(_data, d):
        (d / "relationships.yaml").write_text(yaml.safe_dump({
            "graph_id": "acme.extension.demo.relationships",
            "edges": [{"source_ref": "demo.area.sample-rule",
                       "target_ref": "coach.lifecycle.phase-machine", "relation": "requires"}],
        }, sort_keys=False))
    with pytest.raises(C.CompositionError, match="authored cross-package edge references core node"):
        C.validate_realizes(_temp_ext(tmp_path, m), _core_ids())
