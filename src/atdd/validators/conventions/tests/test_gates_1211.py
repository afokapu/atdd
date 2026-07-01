# URN: test:validate-conventions:convention-graph-query-contract:E020-RED-001-gates
# Acceptance: acc:validate-conventions:E019-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E020-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E021-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E022-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E023-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E024-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E025-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E026-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E020
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""#1211 gates: graph-query contract, vacuity, template-shaped evidence, parity-gate
integrity, stricter-finding adjudication, train representation, harness enum."""
from __future__ import annotations

import json
from pathlib import Path

from atdd.validators.conventions._support import sentinels as S
from atdd.validators.conventions._support import catch_matrix as CM
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


# E022 — every parity case carries a legacy target + injectable fault
def test_parity_cases_are_well_formed() -> None:
    assert CM.CASES, "no parity cases"
    for c in CM.CASES:
        assert c.legacy_target and (c.patch or c.tempfile), f"{c.name} lacks legacy target/fault"


# E023 — parity is claimed only from the catch matrix, with zero clean-repo FPs
def test_parity_claims_come_from_matrix(repo_root: Path) -> None:
    report = repo_root / "docs" / "validator-parity" / "catch-matrix.md"
    assert report.exists(), "catch-matrix report missing — no parity authority"
    text = report.read_text(encoding="utf-8")
    assert "clean-repo false positives (convention flags on clean): **0**" in text, \
        "parity may not be claimed while convention flags the clean baseline"


# E024 — stricter findings are adjudicated
def test_stricter_findings_adjudicated(repo_root: Path) -> None:
    ledger = repo_root / "docs" / "validator-parity" / "stricter-findings-adjudication.md"
    assert ledger.exists(), "adjudication ledger missing"
    text = ledger.read_text(encoding="utf-8")
    for cls in ("real-gap", "schema-bug", "loader-bug"):
        assert cls in text, f"ledger missing class {cls}"
    assert "FIXED" in text, "ledger records no adjudicated/fixed finding"


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
