# URN: test:author-atdd-substrate:package-composition:C009-UNIT-001-extension-orphan-detection
# Acceptance: acc:author-atdd-substrate:C009-UNIT-001-extension-orphan-detection
# WMBT: wmbt:author-atdd-substrate:C009
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C009-UNIT-001 — extension_orphan_nodes flags an owned convention node referenced
by no internal relationship edge, clears nodes referenced by either edge schema
(from/to or source_ref/target_ref), and returns empty when all nodes are wired."""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.planner.commands import compose


def _ext_pkg(tmp_path: Path, node_ids: list[str], edges: list[dict]) -> dict:
    conv_names = []
    for rid in node_ids:
        f = tmp_path / f"{rid}.convention.yaml"
        f.write_text(
            f"schema_version: 1.1.0\nrule_id: {rid}\nkind: rule\nstatus: active\n"
            f"statement: stub\nterms:\n  - term_id: t\n    text: t\n",
            encoding="utf-8",
        )
        conv_names.append(f.name)
    (tmp_path / "relationships.yaml").write_text(
        yaml.safe_dump({"schema_version": "1.0.0", "edges": edges}), encoding="utf-8"
    )
    return {"kind": "extension", "dir": tmp_path, "manifest": {"owns": {"conventions": conv_names}}}


def test_unreferenced_owned_node_is_orphan(tmp_path) -> None:
    pkg = _ext_pkg(tmp_path, ["x.a", "x.b"], [{"from": "x.a", "to": "x.a"}])
    assert compose.extension_orphan_nodes(pkg) == {"x.b"}


def test_all_referenced_no_orphan(tmp_path) -> None:
    pkg = _ext_pkg(tmp_path, ["x.a", "x.b"], [{"from": "x.a", "to": "x.b"}])
    assert compose.extension_orphan_nodes(pkg) == set()


def test_core_edge_schema_also_counts(tmp_path) -> None:
    pkg = _ext_pkg(tmp_path, ["x.a", "x.b"], [{"source_ref": "x.a", "target_ref": "x.b"}])
    assert compose.extension_orphan_nodes(pkg) == set()


def test_no_edges_all_orphans(tmp_path) -> None:
    pkg = _ext_pkg(tmp_path, ["x.a", "x.b"], [])
    assert compose.extension_orphan_nodes(pkg) == {"x.a", "x.b"}
