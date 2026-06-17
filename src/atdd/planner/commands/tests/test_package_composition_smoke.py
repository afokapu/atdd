# Phase: SMOKE
# Layer: integration
"""Package discovery + composition smoke (#1130, #1133).

Proves ATDD can DISCOVER + COMPOSE installed extension/workspace packages into a
protocol view WITHOUT executing any runtime implementation, and that the
graph-composition semantics (#1133) hold:

  realizes is the only cross-package relation · targets derived from realizes ·
  design_candidates cannot be realized · source graphs carry no cross-package edges ·
  composed view materializes derived edges with the provenance triple · two expansion
  modes (core / composed) · `atdd validate package <path>` works against installed core.

Runs against a CI-portable fixture package set (always) and the real
`atdd-extensions/official` packages when present (skip-if-absent).
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

import jsonschema
import pytest
import yaml

from atdd.planner.commands import compose as C
from atdd.planner.commands.author_manifest import extension_targets_satisfied_by

_SRC = pathlib.Path(__file__).resolve().parents[4]            # .../src
_REPO = _SRC.parent
_FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "packages"
_DEMO_EXT = _FIXTURES / "acme.extension.demo"
_NODE_SCHEMA = json.loads(
    (_SRC / "atdd" / "planner" / "schemas" / "author" / "convention-node.schema.json").read_text()
)
_CORE_GRAPH_ID = "atdd.convention.relationships"


def _core_ids() -> set[str]:
    # same package-relative path the CLI uses (Path(atdd.__file__).parent)
    return C.installed_core_node_ids()


def _assert_all_criteria(root: pathlib.Path, core_ids: set[str]) -> list[dict]:
    pkgs = C.discover_packages(root)
    exts = [p for p in pkgs if p["kind"] == "extension"]
    wss = [p for p in pkgs if p["kind"] == "workspace"]
    assert exts, f"(1) no extension package under {root}"
    assert wss, f"(1) no workspace package under {root}"
    ws_by_id = {w["manifest"].get("workspace_id"): w["manifest"] for w in wss}

    for p in pkgs:
        assert p["manifest"], f"(2) empty manifest {p['manifest_path']}"
        C.validate_by_kind(p)                                                 # (3) validate by kind

    for ext in exts:
        d, m = ext["dir"], ext["manifest"]
        owns = (m.get("owns") or {}).get("conventions") or []
        assert owns, f"{m.get('extension_id')} owns no conventions"
        for rel in owns:
            assert (d / rel).exists(), f"(4) owns path missing: {rel}"        # (4)
            jsonschema.validate(yaml.safe_load((d / rel).read_text()), _NODE_SCHEMA)  # (5)

        gp = d / "relationships.yaml"
        if gp.exists():
            g = yaml.safe_load(gp.read_text()) or {}
            assert g.get("graph_id"), f"(6) {gp} missing graph_id"
            assert g["graph_id"] != _CORE_GRAPH_ID, "(7) extension graph separate from core"
            assert g["graph_id"].startswith(m["extension_id"]), "(7) graph_id ext-namespaced"

        # realization gate: resolves, owned, no design_candidate realized, targets derived,
        # no authored cross-package edges. (criteria 8/9 + #1133)
        realized = C.validate_realizes(ext, core_ids)

        composed = C.compose_protocol_view(core_ids, ext, mode="composed")
        core_view = C.compose_protocol_view(core_ids, ext, mode="core")
        assert composed["executed_implementations"] == [], "(10) composition never runs runtime"
        assert composed["contributes"], "(10) composition surfaces contributed nodes"
        assert not composed["targets_unresolved"], f"(8) unresolved targets {composed['targets_unresolved']}"
        # two expansion modes
        assert core_view["derived_edges"] == [], "(core mode) no derived edges"
        if m.get("realizes"):
            assert composed["derived_edges"], "(composed mode) realizes -> derived edges"
            for e in composed["derived_edges"]:
                assert e["derived"] is True and e["relation"] == "realizes"
                prov = e["provenance"]
                assert prov["core_authority"] in core_ids                     # provenance triple
                assert prov["extension_realization"] in composed["contributes"]
                assert "execution_target" in prov
                # design_candidate never realized (9)
                assert prov["core_authority"] not in composed["design_candidates"]
            # reverse index: core_node -> [extension nodes]
            for cn, ens in composed["realization_index"].items():
                assert cn in core_ids and ens

        for entry in ((m.get("depends_on") or {}).get("workspaces") or []):
            prov = ws_by_id.get(entry.get("id"))
            if prov is not None:
                assert extension_targets_satisfied_by(m, prov), f"workspace contract {entry} unsatisfied"
    return exts


def test_fixture_packages_compose():
    exts = _assert_all_criteria(_FIXTURES, _core_ids())
    assert any(e["manifest"]["extension_id"] == "acme.extension.demo" for e in exts)


def test_real_atdd_extensions_compose_if_present():
    """#10 literally: the real atdd.extension.github composes (skip if not checked out)."""
    candidates = [
        _REPO.parent.parent / "atdd-extensions" / "official",
        _REPO.parent / "atdd-extensions" / "official",
    ]
    official = next((c for c in candidates if c.exists()), None)
    if official is None:
        pytest.skip("atdd-extensions/official not checked out beside core")
    exts = _assert_all_criteria(official, _core_ids())
    assert any(e["manifest"]["extension_id"] == "atdd.extension.github" for e in exts)


def test_cli_validate_package_works_against_installed_core():
    """`atdd validate package <fixture-ext>` exits 0 using package-relative core."""
    env = {"PYTHONPATH": str(_SRC), "PATH": __import__("os").environ.get("PATH", "")}
    r = subprocess.run([sys.executable, "-m", "atdd", "validate", "package", str(_DEMO_EXT)],
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, f"validate package failed: {r.stdout}\n{r.stderr}"
    assert "valid against core" in r.stdout


# ─── helper for negative cases: a mutable temp copy of the demo extension ────
def _temp_ext(tmp_path, mutate):
    dst = tmp_path / "acme.extension.demo"
    shutil.copytree(_DEMO_EXT, dst)
    mf = dst / "atdd.extension.yaml"
    data = yaml.safe_load(mf.read_text())
    mutate(data, dst)
    mf.write_text(yaml.safe_dump(data, sort_keys=False))
    return {"kind": "extension", "dir": dst, "manifest_path": mf, "manifest": data}


def test_negative_unresolved_core_node_fails(tmp_path):
    """(11) realizing a non-shipped core node must fail."""
    def m(data, _d):
        data["realizes"].append({"extension_node": "demo.area.sample-rule",
                                 "core_node": "coach.bogus.does-not-exist"})
        data["depends_on"]["targets"]["coach_nodes"].append("coach.bogus.does-not-exist")
    ext = _temp_ext(tmp_path, m)
    with pytest.raises(C.CompositionError, match="does not resolve to a shipped core node"):
        C.validate_realizes(ext, _core_ids())


def test_negative_design_candidate_realization_fails(tmp_path):
    """(12) realizing a design_candidate must fail."""
    def m(data, _d):
        data["realizes"].append({"extension_node": "demo.area.sample-rule",
                                 "core_node": "coach.execution.work-provenance"})
    ext = _temp_ext(tmp_path, m)
    with pytest.raises(C.CompositionError, match="design_candidate .* cannot be realized"):
        C.validate_realizes(ext, _core_ids())


def test_negative_authored_cross_package_edge_fails(tmp_path):
    """(13) an authored extension graph edge that references a core node must fail."""
    def m(_data, d):
        (d / "relationships.yaml").write_text(yaml.safe_dump({
            "graph_id": "acme.extension.demo.relationships",
            "edges": [{"source_ref": "demo.area.sample-rule",
                       "target_ref": "coach.lifecycle.phase-machine", "relation": "requires"}],
        }, sort_keys=False))
    ext = _temp_ext(tmp_path, m)
    with pytest.raises(C.CompositionError, match="authored cross-package edge references core node"):
        C.validate_realizes(ext, _core_ids())
