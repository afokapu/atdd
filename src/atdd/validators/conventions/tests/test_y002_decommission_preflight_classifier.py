# URN: test:validate-conventions:legacy-decommission:Y002-SMOKE-001-seed
# Acceptance: acc:validate-conventions:Y002-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:Y002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""Y002 — the decommission pre-flight classifier correctly partitions the real ready-set.

Runs scripts/decommission_manifest.py::classify over the live checkout and asserts:
  * a known PLATFORM legacy test (no rule binding, no `# Acceptance:` header) is
    labelled PLATFORM and its required steps EXCLUDE repoint + acceptance handling;
  * a known RULE-BOUND legacy validator is labelled RULE-BOUND and its steps include
    the implementation.ref repoint;
  * a known ACCEPTANCE-ANCHORED legacy validator is labelled ACCEPTANCE-ANCHORED and
    its steps include the acceptance retire/re-anchor (the bidirectional-binding catch);
  * every ready row carries a non-empty label set and names the two CI catches where
    they apply — so an operator/worker sees up front what each retirement needs.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

PLATFORM_ANCHOR = "src/atdd/coach/validators/test_urn_traceability.py"
RULE_BOUND_ANCHOR = "src/atdd/coach/validators/test_commit_trailers_binding.py"
ACCEPTANCE_ANCHOR = "src/atdd/coach/validators/test_e026_bypass_inventory_guard.py"


def _load_classifier(repo_root: Path):
    script = repo_root / "scripts" / "decommission_manifest.py"
    spec = importlib.util.spec_from_file_location("decommission_manifest", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_classifier_partitions_real_ready_set(repo_root: Path) -> None:
    mod = _load_classifier(repo_root)
    rows = mod.classify(repo_root)
    by_path = {r["legacy"]: r for r in rows}

    # The classifier runs over a non-trivial real ready-set and every row is labelled.
    assert len(rows) >= 10, f"expected a real ready-set, got {len(rows)}"
    assert all(r["labels"] for r in rows), "every ready candidate must carry >=1 label"

    # --- PLATFORM: clean delete, no repoint, no acceptance handling ---
    plat = by_path.get(PLATFORM_ANCHOR)
    assert plat is not None, f"{PLATFORM_ANCHOR} not in ready-set"
    assert plat["labels"] == ["PLATFORM"], plat["labels"]
    assert not plat["repoint_rules"] and not plat["acceptances"]
    joined = " ".join(plat["required_steps"]).lower()
    assert "repoint" not in joined and "acceptance" not in joined, plat["required_steps"]

    # --- RULE-BOUND: needs the implementation.ref repoint ---
    rb = by_path.get(RULE_BOUND_ANCHOR)
    assert rb is not None, f"{RULE_BOUND_ANCHOR} not in ready-set"
    assert "RULE-BOUND" in rb["labels"], rb["labels"]
    assert rb["repoint_rules"], "rule-bound candidate must name repoint rules"
    assert any("REPOINT" in s for s in rb["required_steps"]), rb["required_steps"]

    # --- ACCEPTANCE-ANCHORED: needs acceptance retire/re-anchor (bidirectional catch) ---
    aa = by_path.get(ACCEPTANCE_ANCHOR)
    assert aa is not None, f"{ACCEPTANCE_ANCHOR} not in ready-set"
    assert "ACCEPTANCE-ANCHORED" in aa["labels"], aa["labels"]
    assert aa["acceptances"], "acceptance-anchored candidate must name acceptances"
    assert any("ACCEPTANCE" in s and mod.CATCH_BINDING in s for s in aa["required_steps"]), \
        aa["required_steps"]

    # The two anchors that differ in kind must not collapse into the same partition.
    assert plat["labels"] != rb["labels"], "platform and rule-bound must partition apart"

    # Both CI catches are named somewhere in the emitted guidance.
    all_steps = " ".join(s for r in rows for s in r["required_steps"])
    assert mod.CATCH_DELETION in all_steps
    assert mod.CATCH_BINDING in all_steps
