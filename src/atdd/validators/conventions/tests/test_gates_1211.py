# URN: test:validate-conventions:convention-graph-query-contract:E020-RED-001-gates
# Acceptance: acc:validate-conventions:E019-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E020-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E021-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E025-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E026-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E020
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""#1211 gates: graph-query contract, vacuity, template-shaped evidence, train
representation, harness enum."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.validators.conventions._support import sentinels as S
from atdd.validators.conventions._support.graph_loader import load_composed_graph

# E019 — graph normalizes real nodes
def test_graph_normalizes_real_nodes(repo_root: Path) -> None:
    g = load_composed_graph(repo_root)
    wagons = g.by_kind("wagon")
    assert wagons, "no wagon nodes"
    w = wagons[0]
    assert w.id and w.kind == "wagon" and w.theme and w.location and isinstance(w.refs, list)
    assert g.by_kind("wmbt") and g.rules(), "graph missing wmbt/rule nodes"


# E020 — vacuity guard: every sentinel selects > 0 real nodes
def test_no_sentinel_selects_vacuously(repo_root: Path) -> None:
    g = load_composed_graph(repo_root)
    vacuous = [name for name, fn in S.SENTINELS.items() if fn(g).selected_nodes == 0]
    assert not vacuous, f"sentinels with zero selection (vacuous pass): {vacuous}"


# E021 — failure evidence is template-shaped
@pytest.mark.convention_filesystem_mutation
def test_evidence_is_template_shaped(repo_root: Path) -> None:
    wagon = repo_root / "plan" / "validate_conventions" / "_validate_conventions.yaml"
    orig = wagon.read_text(encoding="utf-8")
    wagon.write_text(orig.replace("theme: commons", "theme: bogus_noncanonical", 1), encoding="utf-8")
    try:
        r = S.theme_must_be_canonical(load_composed_graph(repo_root))
    finally:
        wagon.write_text(orig, encoding="utf-8")
    allowed = {"node_id", "field", "value", "grammar_name", "node_location"}
    assert r.violations, "no evidence produced to shape-check"
    for ev in r.violations:
        assert set(ev).issubset(allowed), f"evidence not template-shaped: {set(ev)}"


# E025 — train nodes use the conformant detail representation
def test_train_nodes_conformant(repo_root: Path) -> None:
    g = load_composed_graph(repo_root)
    trains = g.by_kind("train")
    assert trains, "no train nodes"
    for t in trains:
        assert "title" in t.fields and t.refs, f"train {t.id} not loaded from detail (no title/refs)"
        for ref in t.refs:
            assert ref.startswith("wagon:"), f"train ref not a wagon: {ref}"


# E026 — acceptance harness enum includes smoke
def test_harness_enum_includes_smoke(repo_root: Path) -> None:
    sc = json.loads((repo_root / "src" / "atdd" / "planner" / "schemas"
                     / "acceptance.schema.json").read_text(encoding="utf-8"))
    enum = sc["properties"]["harness"]["properties"]["type"]["enum"]
    assert "smoke" in enum, "acceptance harness enum still omits 'smoke'"
