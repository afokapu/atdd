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


# ---- declaration -> implementation binding (validator file exists) ----
def test_decl_binding_selects_and_clean(repo_root: Path) -> None:
    r = S.declaration_to_implementation_binding(load_composed_graph(repo_root))
    assert r.selected_nodes >= 50, f"vacuous/low rule selection: {r.selected_nodes}"
    assert r.violations == [], f"repo rule(s) point at missing validator files: {r.violations[:2]}"


def test_decl_binding_catches_missing_impl(repo_root: Path) -> None:
    conv = ('version: "1.0"\nname: "tmp missing impl"\nrules:\n'
            '  - id: "tmp.parity.missing-impl"\n    severity: 3\n'
            '    validator: "test_does_not_exist_zzz::test_x"\n')
    with _temp_convention(repo_root, "src/atdd/coach/conventions/_tmp_missing_impl.convention.yaml", conv):
        r = S.declaration_to_implementation_binding(load_composed_graph(repo_root))
        assert any(v["declaration_node"] == "tmp.parity.missing-impl" for v in r.violations), \
            "decl->impl sentinel missed a rule pointing at a nonexistent validator"


# ---- identifier grammar (wmbt urn) ----
def test_grammar_selects_and_clean(repo_root: Path) -> None:
    r = S.identifier_grammar_conformance(load_composed_graph(repo_root))
    assert r.selected_nodes >= 100, f"vacuous/low wmbt selection: {r.selected_nodes}"
    assert r.violations == [], f"repo wmbt urn(s) violate grammar: {r.violations[:2]}"


def test_grammar_catches_bad_urn(repo_root: Path) -> None:
    bad = "urn: wmbt:validate-conventions:zzz\nstep: execute\n"
    with _temp_convention(repo_root, "plan/validate_conventions/ZZTMP.yaml", bad):
        r = S.identifier_grammar_conformance(load_composed_graph(repo_root))
        assert any(v["value"] == "wmbt:validate-conventions:zzz" for v in r.violations), \
            "grammar sentinel missed a malformed wmbt urn"


# ---- composition (all sources parse) ----
def test_composition_selects_and_clean(repo_root: Path) -> None:
    r = S.composed_graph_loads(load_composed_graph(repo_root))
    assert r.selected_nodes > 100, f"vacuous: composed graph has {r.selected_nodes} nodes"
    assert r.violations == [], f"repo has unparseable convention sources: {r.violations[:2]}"


def test_composition_catches_parse_error(repo_root: Path) -> None:
    with _temp_convention(repo_root, "src/atdd/coach/conventions/_tmp_bad.convention.yaml",
                          "name: [unterminated\n"):
        r = S.composed_graph_loads(load_composed_graph(repo_root))
        assert any("_tmp_bad" in v["source_file"] for v in r.violations), \
            "composition sentinel missed an unparseable source"


# ---- artifact reference resolution (file refs exist) ----
def test_artifact_selects_and_clean(repo_root: Path) -> None:
    r = S.artifact_reference_resolution(load_composed_graph(repo_root))
    assert r.selected_nodes > 0 and r.checked_edges > 0, "vacuous: no artifact refs checked"
    assert r.violations == [], f"repo has dangling artifact refs: {r.violations[:2]}"


def test_artifact_catches_missing_file(repo_root: Path) -> None:
    feat = ("urn: feature:validate-conventions:tmp-artifact\n"
            "wagon: wagon:validate-conventions\nreferences:\n- docs/NONEXISTENT_ZZZ.md\n")
    with _temp_convention(repo_root, "plan/validate_conventions/features/_tmp_artifact.yaml", feat):
        r = S.artifact_reference_resolution(load_composed_graph(repo_root))
        assert any(v["artifact_ref"] == "docs/NONEXISTENT_ZZZ.md" for v in r.violations), \
            "artifact sentinel missed a dangling file reference"


# ---- node schema conformance (wagon) ----
def test_schema_selects_and_clean(repo_root: Path) -> None:
    r = S.node_schema_conformance(load_composed_graph(repo_root))
    assert r.selected_nodes > 0, "vacuous: no schema-validated nodes"
    assert r.violations == [], f"repo wagon(s) violate wagon.schema: {r.violations[:2]}"


def test_schema_catches_missing_required(repo_root: Path) -> None:
    with _patched(repo_root, WAGON, "subject: agent:tester\n", ""):
        r = S.node_schema_conformance(load_composed_graph(repo_root))
        assert any(v["node_id"] == "wagon:validate-conventions" for v in r.violations), \
            "schema sentinel missed a wagon missing a required field"


def test_roundtrip_selects_and_clean(repo_root: Path) -> None:
    """Non-vacuous on real data AND clean: every migrated (dispositioned) rule's
    declared validator binds its own id. (The earlier 'finds gaps on real data'
    assertion relied on false positives from a literal-only bind_rule scan; those
    were fixed in graph_loader, so the real baseline is now correctly 0.)"""
    r = S.rule_validator_roundtrip(load_composed_graph(repo_root))
    assert r.selected_nodes > 0, "vacuous: no dispositioned rules with validators selected"
    assert r.violations == [], f"repo has real roundtrip gaps: {r.violations[:2]}"


# ---- single-node ingestion (atdd author nodes are visible to the engine) (#1212) ----
def test_single_node_authored_rules_in_graph(repo_root: Path) -> None:
    """The two-pass loader must node-ify single-node `<role>/conventions/nodes/
    <rule_id>.convention.yaml` files (top-level `rule_id`, no `rules:` block) as rule
    nodes — not just `rules:[]` blocks. Proven by a known authored rule_id being
    visible in g.rules(), and by the corpus growing well past the blocks-only count."""
    g = load_composed_graph(repo_root)
    rule_ids = {n.id for n in g.rules()}
    assert "planner.feature.size-max-rule" in rule_ids, (
        "single-node authored rule_id 'planner.feature.size-max-rule' is invisible to "
        "the engine — two-pass single-node ingestion did not run")
    # An authored anti_pattern node (no implementation/validator) is also ingested.
    assert "planner.artifact-naming.anti-patterns" in rule_ids
    # blocks-only baseline was 152; single-node ingestion lifts the corpus well past it.
    assert len(rule_ids) >= 250, f"expected ~270 rules after ingestion, got {len(rule_ids)}"


def test_single_node_migration_overlap_not_duplicated(repo_root: Path) -> None:
    """A rule_id present BOTH in a `rules:[]` block and as a single-node file is the
    same rule in two representations — pass 2 must skip it so it is not a duplicate."""
    r = S.scoped_identifier_uniqueness(load_composed_graph(repo_root))
    assert r.violations == [], (
        f"migration-overlap rule_ids double-counted as duplicates: {r.violations[:3]}")


def test_single_node_ref_variants_bind(repo_root: Path) -> None:
    """The three single-node `implementation.ref` forms (module::function, rule-id
    cross-reference, bare function name) must all resolve to a real validator — clean
    binding baseline = 0, with no single-node node silently exempted."""
    g = load_composed_graph(repo_root)
    r = S.declaration_to_implementation_binding(g)
    assert r.violations == [], (
        f"single-node implementation.ref(s) do not bind to a real validator: "
        f"{r.violations[:5]}")
    # Confirm the resolver is actually exercised by a single-node node (not just blocks):
    assert any(n.location.endswith(".convention.yaml") and "/nodes/" in n.location
               and n.validator for n in g.rules()), \
        "no single-node node with an implementation.ref was ingested"


def test_roundtrip_catches_unbound_validator(repo_root: Path) -> None:
    """Fault injection: a dispositioned rule whose declared validator file exists but
    never bind_rule()s this id must be flagged (the legacy reverse-coherence class)."""
    conv = ('version: "1.0"\nname: "tmp roundtrip"\nrules:\n'
            '  - id: "coach.tmp.roundtrip-probe"\n    severity: 3\n'
            '    disposition: strict\n'
            '    validator: "test_theme_must_be_canonical::test_every_wagon_theme_is_canonical"\n')
    with _temp_convention(repo_root,
                          "src/atdd/coach/conventions/_tmp_roundtrip_probe.convention.yaml", conv):
        r = S.rule_validator_roundtrip(load_composed_graph(repo_root))
        assert any(v["declaration_id"] == "coach.tmp.roundtrip-probe" for v in r.violations), \
            "roundtrip sentinel missed a rule whose declared validator does not bind it"
