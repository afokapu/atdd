"""
Detect stub-body presentation components in TypeScript / TSX.

A presentation component is a *stub* when its render body is statically
provable to produce no visible DOM. Stub patterns detected here:

* ``() => null`` / ``() => undefined``                       → PRESENTATION-NOSTUB-001
* function block whose only return is ``null``/``undefined``/bare → PRESENTATION-NOSTUB-002
* ``return <></>`` / ``return <Fragment></Fragment>`` (no children) → PRESENTATION-NOSTUB-003
* ``return <div />`` (zero children, zero dynamic attributes)  → PRESENTATION-NOSTUB-004
* unconditional stub (e.g. ``flag ? null : null``)            → PRESENTATION-NOSTUB-005
* allowlist entry without ``migration:`` field                → PRESENTATION-NOSTUB-010 (sev=2)

Real incident behind this rule (issue #318): ``jel-app`` shipped
``export const AuthGateShell = () => null;`` to production. Every existing
ATDD validator was green because none read the rendered body.

Convention: ``src/atdd/coder/conventions/frontend.convention.yaml``
            (rule family ``no_stub_presentation``)

Structured violations: emits ``Violation(rule_id="PRESENTATION-NOSTUB-NNN", ...)``
records via ``RatchetBaseline.assert_no_regression(violations=...)``.
The rule-id grammar is governed by ``src/atdd/coach/specs/rule-id.spec.md``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest
import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import load_atdd_config
from atdd.coach.validators._violation import Violation


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
FRONTEND_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "frontend.convention.yaml"

FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "stub_presentation"
)


# ---------------------------------------------------------------------------
# Rule constants (mirrored in frontend.convention.yaml::no_stub_presentation)
# ---------------------------------------------------------------------------
RULE_ARROW_LITERAL = "PRESENTATION-NOSTUB-001"
RULE_FN_RETURN_LITERAL = "PRESENTATION-NOSTUB-002"
RULE_EMPTY_FRAGMENT = "PRESENTATION-NOSTUB-003"
RULE_EMPTY_ELEMENT = "PRESENTATION-NOSTUB-004"
RULE_UNCONDITIONAL_STUB = "PRESENTATION-NOSTUB-005"
RULE_ALLOWLIST_MIGRATION = "PRESENTATION-NOSTUB-010"

STUB_RULE_SEVERITY = 4
ALLOWLIST_RULE_SEVERITY = 2

ALL_RULE_IDS = (
    RULE_ARROW_LITERAL,
    RULE_FN_RETURN_LITERAL,
    RULE_EMPTY_FRAGMENT,
    RULE_EMPTY_ELEMENT,
    RULE_UNCONDITIONAL_STUB,
    RULE_ALLOWLIST_MIGRATION,
)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------
_SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", ".nuxt",
    "coverage", "__pycache__", ".cache", "__tests__", "__mocks__",
    ".venv", "venv", "fixtures",
}
_TS_EXTENSIONS = {".tsx"}  # First-cut TSX-only per Decision #7.


def _is_excluded(path: Path) -> bool:
    """Skip tests, fixtures, and non-presentation paths."""
    p = str(path)
    if "/fixtures/" in p:
        return True
    if "/__tests__/" in p or "/tests/" in p or "/test/" in p:
        return True
    name = path.name
    if name.endswith((".test.tsx", ".spec.tsx")):
        return True
    return False


def _is_presentation_path(path: Path) -> bool:
    """Component is in scope only when the file lives under a ``presentation/`` segment."""
    return "/presentation/" in str(path).replace("\\", "/")


def _collect_tsx_files(scan_dirs: List[str]) -> List[Path]:
    """Walk scan_dirs and collect TSX files inside presentation/ segments."""
    out: List[Path] = []
    for scan_dir in scan_dirs:
        base = REPO_ROOT / scan_dir
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                if not any(fname.endswith(ext) for ext in _TS_EXTENSIONS):
                    continue
                fp = Path(dirpath) / fname
                if _is_excluded(fp):
                    continue
                if not _is_presentation_path(fp):
                    continue
                out.append(fp)
    return sorted(out)


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------
def _load_config() -> Dict:
    """Load no_stub_presentation block from .atdd/config.yaml."""
    config = load_atdd_config(REPO_ROOT)
    return config.get("no_stub_presentation", {}) or {}


def _load_allowlist(cfg: Dict) -> Dict[str, str]:
    """Build path → migration map from allowlist entries."""
    allowed: Dict[str, str] = {}
    for entry in cfg.get("allowlist", []) or []:
        path = (entry.get("path") or "").strip()
        migration = (entry.get("migration") or "").strip()
        if path:
            allowed[path] = migration
    return allowed


# ---------------------------------------------------------------------------
# Detection (RED-phase placeholder — implemented in GREEN)
# ---------------------------------------------------------------------------
def detect_stub_returns(file_path: Path) -> List[Violation]:
    """Return ``Violation`` records for every stub-return component in *file_path*.

    RED-phase placeholder: real AST detection lives in GREEN. Returning an
    empty list here makes the fixture-violation tests fail until the AST
    walker is implemented.
    """
    return []


# ---------------------------------------------------------------------------
# Scan helper for ratchet baseline registry (filled in GREEN)
# ---------------------------------------------------------------------------
def scan_stub_presentation_returns(repo_root: Path) -> Tuple[int, List[Violation]]:
    """Aggregate stub-return violations across configured scan_dirs."""
    cfg = _load_config()
    scan_dirs = cfg.get("scan_dirs", []) or []
    if not scan_dirs:
        return 0, []
    allowlist = _load_allowlist(cfg)
    files = _collect_tsx_files(scan_dirs)
    violations: List[Violation] = []
    for f in files:
        try:
            rel = str(f.relative_to(repo_root))
        except ValueError:
            rel = str(f)
        if rel in allowlist:
            continue
        violations.extend(detect_stub_returns(f))
    return len(violations), violations


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.coder
def test_stub_fixture_violations_detected():
    """
    PRESENTATION-NOSTUB-001..005: every seeded stub fixture emits a Violation.

    Given: fixtures/stub_presentation/{arrow_null, fn_return_null, empty_fragment,
           empty_div, ternary_both_null}.tsx + jel_app_repro/AuthGateShell.tsx
    When:  detect_stub_returns runs
    Then:  each fixture produces at least one Violation with the canonical
           rule_id and severity=4.
    """
    expectations = {
        "arrow_null.tsx": RULE_ARROW_LITERAL,
        "fn_return_null.tsx": RULE_FN_RETURN_LITERAL,
        "empty_fragment.tsx": RULE_EMPTY_FRAGMENT,
        "empty_div.tsx": RULE_EMPTY_ELEMENT,
        "ternary_both_null.tsx": RULE_UNCONDITIONAL_STUB,
    }

    failures: List[str] = []
    for fname, expected_rule in expectations.items():
        fixture = FIXTURES_DIR / fname
        if not fixture.exists():
            failures.append(f"  Missing fixture: {fixture}")
            continue
        violations = detect_stub_returns(fixture)
        if not violations:
            failures.append(f"  {fname}: no violation emitted (expected {expected_rule})")
            continue
        rule_ids = {v.rule_id for v in violations}
        if expected_rule not in rule_ids:
            failures.append(
                f"  {fname}: expected {expected_rule}, got {sorted(rule_ids)}"
            )
        for v in violations:
            if v.severity != STUB_RULE_SEVERITY:
                failures.append(
                    f"  {fname}: {v.rule_id} severity={v.severity}, expected {STUB_RULE_SEVERITY}"
                )

    repro = FIXTURES_DIR / "jel_app_repro" / "AuthGateShell.tsx"
    if not repro.exists():
        failures.append(f"  Missing jel-app repro: {repro}")
    else:
        repro_violations = detect_stub_returns(repro)
        if not any(v.rule_id == RULE_ARROW_LITERAL for v in repro_violations):
            failures.append(
                f"  jel_app_repro/AuthGateShell.tsx: expected {RULE_ARROW_LITERAL}, "
                f"got {[v.rule_id for v in repro_violations]}"
            )

    if failures:
        pytest.fail("Stub-detection misses:\n" + "\n".join(failures))


@pytest.mark.coder
def test_stub_fixture_clean_no_false_positives():
    """
    PRESENTATION-NOSTUB-020 (negative rule): legitimate components do not flag.

    Given: conditional_null_ok.tsx (guarded null + sibling JSX return) and
           passthrough_children_ok.tsx (returns <div>{children}</div>)
    When:  detect_stub_returns runs
    Then:  zero Violations.
    """
    clean_fixtures = ["conditional_null_ok.tsx", "passthrough_children_ok.tsx"]

    spurious: List[str] = []
    for fname in clean_fixtures:
        fixture = FIXTURES_DIR / fname
        if not fixture.exists():
            pytest.fail(f"Missing fixture: {fixture}")
        for v in detect_stub_returns(fixture):
            spurious.append(f"  {fname}: {v}")

    if spurious:
        pytest.fail("False positives on legitimate components:\n" + "\n".join(spurious))


@pytest.mark.coder
def test_allowlist_entries_have_migration_references():
    """
    PRESENTATION-NOSTUB-010: every allowlist entry must reference a migration issue.

    Given: no_stub_presentation.allowlist in .atdd/config.yaml
    When:  iterating entries
    Then:  entries without migration references emit a sev=2 Violation.
    """
    cfg = _load_config()
    entries = cfg.get("allowlist", []) or []

    if not entries:
        pytest.skip("No no_stub_presentation.allowlist entries in .atdd/config.yaml")

    violations: List[Violation] = []
    for entry in entries:
        path = (entry.get("path") or "").strip()
        migration = (entry.get("migration") or "").strip()
        if not migration:
            violations.append(Violation(
                rule_id=RULE_ALLOWLIST_MIGRATION,
                severity=ALLOWLIST_RULE_SEVERITY,
                location=f".atdd/config.yaml:{path or '<missing path>'}",
                detail="allowlist entry missing migration: reference",
            ))

    if violations:
        pytest.fail(
            f"\n{len(violations)} allowlist entry/entries missing migration:\n"
            + "\n".join(f"  {v}" for v in violations)
        )


@pytest.mark.coder
def test_no_stub_presentation_returns(ratchet_baseline):
    """
    PRESENTATION-NOSTUB-001..005 ratchet: no stub-return regressions.

    Scans configured scan_dirs and uses ratchet baseline so pre-existing
    violations are tolerated until they are migrated, but new violations fail.

    Given: TSX files under no_stub_presentation.scan_dirs (presentation/ only)
    When:  AST scan for stub-body return patterns
    Then:  violation count does not exceed baseline (auto-seeds first run)
    """
    cfg = _load_config()
    scan_dirs = cfg.get("scan_dirs", []) or []
    if not scan_dirs:
        pytest.skip(
            "no_stub_presentation.scan_dirs not configured in .atdd/config.yaml — "
            "consumer repo must opt in"
        )

    count, violations = scan_stub_presentation_returns(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="no_stub_presentation_returns",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_no_stub_presentation_rules_declared_in_convention():
    """
    PRESENTATION-NOSTUB-NNN convention contract: each rule is declared with
    the expected severity in frontend.convention.yaml::no_stub_presentation.
    """
    if not FRONTEND_CONVENTION.exists():
        pytest.fail(f"Missing convention: {FRONTEND_CONVENTION}")

    with open(FRONTEND_CONVENTION, "r", encoding="utf-8") as fh:
        convention = yaml.safe_load(fh)

    block = (convention.get("no_stub_presentation") or {})
    rules_by_id = {r.get("id"): r for r in block.get("rules", []) or []}

    expected_severity = {
        RULE_ARROW_LITERAL: STUB_RULE_SEVERITY,
        RULE_FN_RETURN_LITERAL: STUB_RULE_SEVERITY,
        RULE_EMPTY_FRAGMENT: STUB_RULE_SEVERITY,
        RULE_EMPTY_ELEMENT: STUB_RULE_SEVERITY,
        RULE_UNCONDITIONAL_STUB: STUB_RULE_SEVERITY,
        RULE_ALLOWLIST_MIGRATION: ALLOWLIST_RULE_SEVERITY,
    }

    missing: List[str] = []
    for rid, sev in expected_severity.items():
        if rid not in rules_by_id:
            missing.append(f"  {rid}: not declared in no_stub_presentation.rules")
            continue
        decl_sev = rules_by_id[rid].get("severity")
        if decl_sev != sev:
            missing.append(f"  {rid}: declared severity={decl_sev}, expected {sev}")

    if missing:
        pytest.fail(
            f"frontend.convention.yaml::no_stub_presentation drift:\n"
            + "\n".join(missing)
        )
