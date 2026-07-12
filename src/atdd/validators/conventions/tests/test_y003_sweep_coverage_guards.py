# URN: test:validate-conventions:legacy-decommission:Y003-SMOKE-guards
# Acceptance: acc:validate-conventions:Y003-SMOKE-001-no-dangling-legacy-reference
# Acceptance: acc:validate-conventions:Y003-SMOKE-002-coverage-preserved
# WMBT: wmbt:validate-conventions:Y003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""Y003 — the two permanent decommission guards (#1365 sweep).

These outlive the migration scaffolding (Y001/Y002 were migration-only and were torn
down with the parity machinery in #1385). They are the permanent hygiene that proves the
sweep moved coverage to the convention layer instead of dropping it:

  Y003-SMOKE-001  no-dangling-legacy-reference — no rule's ``validator``/``implementation.ref``
                  that names a test FILE (a ``test_*`` binding) resolves to a non-existent
                  path. Successor to the retired Y001 (legacy-validator-map safety) at the rule-ref level.

  Y003-SMOKE-002  coverage-preserved — every rule swept off a retired legacy validator now
                  binds to a convention variant under ``…/validators/conventions/`` that
                  EXECUTES (Phase GREEN, a real fault/parity test), not a persona-folder file
                  or an xfail/stub. Successor to the retired Y002 (preflight classification): it
                  asserts the replacement coverage actually runs.

RED note: SMOKE-002 fails until the GREEN sweep repoints the rules (they still bind to the
persona-folder legacy files at RED). Both go green once the sweep lands.
"""
from __future__ import annotations

import glob
import re
from pathlib import Path

import yaml

PERSONA_DIRS = ("planner", "tester", "coder", "coach")
CONV_REL = "src/atdd/validators/conventions"

# The sweep's coverage map (docs/validator-parity/decommission-sweep-manifest-1365.md §a):
# each rule repointed off a retired legacy validator -> the convention variant file that now
# carries its coverage. Explicit so a regressed repoint fails loudly. (PLATFORM/no-rule legacy
# files — urn_traceability — and the MAP-BLOCKED acceptance-only files carry no rule and are
# intentionally absent.)
SWEPT_RULE_TO_VARIANT = {
    "coach.rule-id.fix-hint-completeness": "presence/test_rule_has_fix_hint.py",
    "planner.train.dispatch-map-is-registry": "schema/test_dispatch_map_is_registry.py",
    "planner.train.dispatch-composite-key-exceptional": "schema/test_dispatch_map_is_registry.py",
    "planner.smoke.feedback-loop-close-the-loop": "presence/test_feedback_loop_close_the_loop.py",
    "coder.coverage.every-feature-must-have": "coverage/test_hierarchy_coverage.py",
    "coder.coverage.every-implementation-must-have": "coverage/test_hierarchy_coverage.py",
    "coder.design.hierarchy-coverage": "coverage/test_hierarchy_coverage.py",
    "planner.coverage.every-wmbt-must-have": "coverage/test_hierarchy_coverage.py",
    "tester.coverage.tracking-manifest-must-be": "coverage/test_hierarchy_coverage.py",
    "planner.wagon.no-consume-cycle": "acyclicity/test_no_cross_wagon_consume_cycle.py",
    "planner.relationship.no-orphan-nodes": "coverage/test_no_orphan_nodes.py",
    "planner.smoke.synthetic-fixture-bypass": "policy/test_smoke_synthetic_fixture_bypass.py",
    "planner.theme.commons-coach-boundary": "boundary/test_theme_commons_coach_boundary.py",
    "planner.theme.urn-namespace-matches": "coherence/test_theme_urn_namespace_matches.py",
    "planner.theme.theme-zero-mandatory": "presence/test_theme_zero_mandatory.py",
    "planner.train.registry": "resolution/test_train_validation.py",
    "planner.wagon.coupling-complexity": "sizing/test_wagon_coupling_complexity.py",
    "planner.wagon.separability": "sizing/test_wagon_separability.py",
    "planner.wmbt.must-have-smoke-acceptance": "coverage/test_wmbt_has_smoke_acceptance.py",
}


def _all_rule_refs(root: Path) -> dict[str, str]:
    """rule_id -> its declared ``validator``/``implementation.ref`` across all convention YAMLs.

    Covers both list-style rule blocks (``- id:`` + ``validator:``) and single-node conventions
    (``rule_id:`` + ``implementation.ref:``), including rules nested under sections (smoke.convention).
    """
    out: dict[str, str] = {}

    def walk(o):
        if isinstance(o, dict):
            rid = o.get("id") or o.get("rule_id")
            if rid:
                ref = o.get("validator")
                impl = o.get("implementation")
                if not ref and isinstance(impl, dict):
                    ref = impl.get("ref") or impl.get("validator")
                if ref:
                    out.setdefault(rid, ref)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for f in glob.glob(str(root / "src/atdd/**/conventions/**/*.yaml"), recursive=True):
        try:
            walk(yaml.safe_load(Path(f).read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def _is_test_file_binding(ref: str) -> bool:
    """True iff ref names a test FILE (``test_*``), not a rule-id cross-reference."""
    base = ref.split("::", 1)[0].rsplit("/", 1)[-1]
    if base.endswith(".py"):
        base = base[:-3]
    return base.startswith("test_")


def _candidate_paths(ref: str, root: Path) -> list[Path]:
    stem = ref.split("::", 1)[0]
    if stem.endswith(".py"):
        stem = stem[:-3]
    if "/" in stem:
        # try as-is, and with the validators/ and src/atdd/ prefixes (refs use short forms
        # like ``conventions/presence/test_x`` or ``src/atdd/validators/conventions/...``)
        return [
            root / (stem + ".py"),
            root / "src/atdd/validators" / (stem + ".py"),
            root / "src/atdd" / (stem + ".py"),
        ]
    # Bare stem = a persona-folder binding (convention variants are ALWAYS referenced by a
    # ``conventions/…`` path, never a bare stem). Resolve ONLY against the persona validator
    # dirs — do NOT fall back to a same-stemmed convention variant, or a rule still pointing at
    # a DELETED persona file whose stem collides with a surviving variant would be missed
    # (the exact same-stem case: test_train_validation / test_no_hardcoded_rule_severity / …).
    return [root / f"src/atdd/{d}/validators/{stem}.py" for d in PERSONA_DIRS]


def _variant_executes(vf: Path) -> bool:
    if not vf.exists():
        return False
    txt = vf.read_text(encoding="utf-8")
    if "# Phase: GREEN" not in txt:
        return False
    return bool(re.search(r"def test_\w*(fault|parity|catches|convention|legacy)", txt))


def test_y003_smoke_001_no_dangling_legacy_reference(repo_root: Path) -> None:
    """No rule's test-file binding resolves to a non-existent file."""
    refs = _all_rule_refs(repo_root)
    dangling = []
    for rid, ref in sorted(refs.items()):
        if not _is_test_file_binding(ref):
            continue  # rule-id cross-reference, not a file binding
        cands = _candidate_paths(ref, repo_root)
        if not any(c.exists() for c in cands):
            dangling.append((rid, ref))
    assert not dangling, "rules whose test-file binding is dangling (deleted target): " + repr(dangling)

    # self-check: a ref to a non-existent persona-folder file MUST be detectable as dangling.
    synthetic = "test_deleted_by_sweep_does_not_exist::test_x"
    assert _is_test_file_binding(synthetic)
    assert not any(c.exists() for c in _candidate_paths(synthetic, repo_root))


def test_y003_smoke_002_coverage_preserved(repo_root: Path) -> None:
    """Every swept rule now binds to a convention variant that executes (not persona-folder)."""
    refs = _all_rule_refs(repo_root)
    failures = []
    for rid, variant_rel in sorted(SWEPT_RULE_TO_VARIANT.items()):
        ref = refs.get(rid)
        if not ref:
            failures.append((rid, None, "rule declaration not found"))
            continue
        if "validators/conventions/" not in ref and "conventions/" not in ref:
            failures.append((rid, ref, "not repointed to a conventions/ variant"))
            continue
        vf = repo_root / CONV_REL / variant_rel
        if not _variant_executes(vf):
            failures.append((rid, variant_rel, "variant does not execute (not GREEN/real-fault)"))
    assert not failures, "coverage NOT preserved after sweep: " + repr(failures)
