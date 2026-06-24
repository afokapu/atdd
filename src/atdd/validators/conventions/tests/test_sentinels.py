# URN: test:validate-conventions:p0-graph-integrity-variants:E010-RED-001-sentinels
# Acceptance: acc:validate-conventions:E010-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E010
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""Three sentinel validators proving the approach against the REAL composed graph.

Each proves a level the fixture harness could not:
  - non-vacuous selection (selector inspects real repo nodes; cardinality > 0),
  - real-fault detection on disk (inject -> reload -> caught -> revert),
  - and for theme: BLACK-BOX parity vs the actual legacy pytest validator.

If these three cannot work on the real graph, the architecture is not ready.
"""
from __future__ import annotations

import contextlib
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.validators.conventions._support import sentinels as S
from atdd.validators.conventions._support.graph_loader import load_composed_graph

WAGON = Path("plan/validate_conventions/_validate_conventions.yaml")


@contextlib.contextmanager
def _patched(repo_root: Path, rel: Path, old: str, new: str):
    p = repo_root / rel
    orig = p.read_text(encoding="utf-8")
    assert old in orig, f"anchor {old!r} not found in {rel}"
    p.write_text(orig.replace(old, new, 1), encoding="utf-8")
    try:
        yield
    finally:
        p.write_text(orig, encoding="utf-8")


# ---- theme sentinel (node-field inspection) ----
def test_theme_selects_real_wagons_and_clean(repo_root: Path) -> None:
    r = S.theme_must_be_canonical(load_composed_graph(repo_root))
    assert r.selected_nodes > 0, "vacuous: theme selector inspected zero wagons"
    assert r.selected_nodes >= 20, f"expected most wagons selected, got {r.selected_nodes}"
    assert r.violations == [], f"repo unexpectedly has non-canonical themes: {r.violations}"


def test_theme_catches_injected_noncanonical(repo_root: Path) -> None:
    with _patched(repo_root, WAGON, "theme: commons", "theme: bogus_noncanonical"):
        r = S.theme_must_be_canonical(load_composed_graph(repo_root))
        assert any(v["value"] == "bogus_noncanonical" for v in r.violations), \
            "theme sentinel failed to catch an injected non-canonical theme"


def test_theme_blackbox_parity_vs_legacy(repo_root: Path) -> None:
    """Inject one fault; BOTH the legacy pytest validator and the convention
    sentinel must catch it (same failure class)."""
    legacy = "src/atdd/planner/validators/test_theme_must_be_canonical.py::test_every_wagon_theme_is_canonical"
    with _patched(repo_root, WAGON, "theme: commons", "theme: bogus_noncanonical"):
        legacy_rc = subprocess.run(
            [sys.executable, "-m", "pytest", legacy, "-q", "-p", "no:cacheprovider"],
            cwd=repo_root, env={"PYTHONPATH": "src", "PATH": __import__("os").environ["PATH"]},
            capture_output=True, text=True,
        ).returncode
        conv = S.theme_must_be_canonical(load_composed_graph(repo_root))
    legacy_caught = legacy_rc != 0
    conv_caught = bool(conv.violations)
    assert legacy_caught and conv_caught, (
        f"parity break: legacy_caught={legacy_caught} convention_caught={conv_caught} "
        "(both must catch the same injected fault)"
    )


# ---- resolution sentinel (real traversal) ----
def test_resolution_selects_and_traverses_clean(repo_root: Path) -> None:
    r = S.direct_reference_resolution(load_composed_graph(repo_root))
    assert r.selected_nodes > 0 and r.checked_edges > 0, "vacuous: no refs traversed"
    assert r.violations == [], f"repo unexpectedly has dangling refs: {r.violations[:3]}"


def test_resolution_catches_dangling_ref(repo_root: Path) -> None:
    with _patched(repo_root, WAGON,
                  "- urn: feature:validate-conventions:family-template-catalogue",
                  "- urn: feature:validate-conventions:family-template-catalogue\n- urn: feature:validate-conventions:GHOST-NONEXISTENT"):
        # GHOST is referenced by the wagon but no such feature node exists
        g = load_composed_graph(repo_root)
        wagon = g.by_id("wagon:validate-conventions")
        assert "feature:validate-conventions:GHOST-NONEXISTENT" in wagon.refs
        r = S.direct_reference_resolution(g)
        assert any(v["missing_ref"] == "feature:validate-conventions:GHOST-NONEXISTENT"
                   for v in r.violations), "resolution sentinel missed a dangling ref"


# ---- binding sentinel (rule -> validator -> emitted rule_id roundtrip) ----
def test_binding_selects_real_rules(repo_root: Path) -> None:
    r = S.rule_validator_roundtrip(load_composed_graph(repo_root))
    assert r.selected_nodes > 0, "vacuous: no rules selected"
    assert r.selected_nodes >= 50, f"expected many rules with validators, got {r.selected_nodes}"


@contextlib.contextmanager
def _temp_convention(repo_root: Path, rel: str, content: str):
    p = repo_root / rel
    p.write_text(content, encoding="utf-8")
    try:
        yield
    finally:
        p.unlink(missing_ok=True)


# ---- uniqueness sentinel (rule-id uniqueness) ----
def test_uniqueness_selects_real_rules_and_clean(repo_root: Path) -> None:
    r = S.scoped_identifier_uniqueness(load_composed_graph(repo_root))
    assert r.selected_nodes > 0 and r.selected_nodes >= 50, \
        f"vacuous/low rule selection: {r.selected_nodes}"
    assert r.violations == [], f"repo unexpectedly has duplicate rule ids: {r.violations[:2]}"


def test_uniqueness_blackbox_parity_vs_legacy(repo_root: Path) -> None:
    """Inject a duplicate rule id; BOTH legacy uniqueness validator and the
    convention sentinel must catch it."""
    dup = ('version: "1.0"\nname: "tmp parity dup"\nrules:\n'
           '  - id: "planner.theme.must-be-canonical"\n    severity: 3\n'
           '    validator: "x::y"\n')
    rel = "src/atdd/coach/conventions/_tmp_parity_dup.convention.yaml"
    legacy = "src/atdd/coach/validators/test_rule_id_uniqueness.py"
    with _temp_convention(repo_root, rel, dup):
        legacy_rc = subprocess.run(
            [sys.executable, "-m", "pytest", legacy, "-q", "-p", "no:cacheprovider"],
            cwd=repo_root, env={"PYTHONPATH": "src", "PATH": __import__("os").environ["PATH"]},
            capture_output=True, text=True,
        ).returncode
        conv = S.scoped_identifier_uniqueness(load_composed_graph(repo_root))
    legacy_caught = legacy_rc != 0
    conv_caught = any(v["duplicate_id"] == "planner.theme.must-be-canonical"
                      for v in conv.violations)
    assert legacy_caught and conv_caught, (
        f"parity break: legacy_caught={legacy_caught} convention_caught={conv_caught}")


# ---- reference-chain sentinel (multi-hop traversal) ----
def test_chain_selects_and_traverses_clean(repo_root: Path) -> None:
    r = S.reference_chain_resolution(load_composed_graph(repo_root))
    assert r.selected_nodes > 0 and r.checked_edges > 0, "vacuous: no chains walked"
    assert r.violations == [], f"repo unexpectedly has broken ref chains: {r.violations[:2]}"


def test_chain_catches_broken_hop(repo_root: Path) -> None:
    with _patched(repo_root, WAGON,
                  "- urn: feature:validate-conventions:family-template-catalogue",
                  "- urn: feature:validate-conventions:family-template-catalogue\n- urn: feature:validate-conventions:GHOST-CHAIN"):
        r = S.reference_chain_resolution(load_composed_graph(repo_root))
        assert any(v["failed_hop"] == "feature:validate-conventions:GHOST-CHAIN"
                   for v in r.violations), "chain sentinel missed a broken hop"


def test_binding_detects_real_roundtrip_gaps(repo_root: Path) -> None:
    """Proves the sentinel detects on REAL data: it finds rules whose declared
    validator does not bind_rule(rule.id) (same class the legacy literal-bind
    coherence scanner enforces)."""
    r = S.rule_validator_roundtrip(load_composed_graph(repo_root))
    ids = {v["declaration_id"] for v in r.violations}
    assert ids, "binding sentinel found no roundtrip gaps on real data (expected >=1)"
