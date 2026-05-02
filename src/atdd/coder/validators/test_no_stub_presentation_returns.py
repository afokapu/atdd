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
from atdd.coder.validators._ast_tsx import parse_tsx, TSXParserUnavailable


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


def _collect_tsx_files(scan_dirs: List[str], repo_root: Path = REPO_ROOT) -> List[Path]:
    """Walk scan_dirs (resolved relative to *repo_root*) and collect TSX files
    inside ``presentation/`` segments. The *repo_root* parameter is used by
    SMOKE tests that scan tmp trees instead of the real repo.
    """
    out: List[Path] = []
    for scan_dir in scan_dirs:
        base = repo_root / scan_dir
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
# AST detection — Decision #2: tree-sitter-typescript, not regex.
# ---------------------------------------------------------------------------
# Stub classification tags returned by `_classify_stub_expr`.
_TAG_LITERAL = "literal"            # null | undefined | bare return
_TAG_UNCONDITIONAL = "unconditional"  # ternary / parens that resolves to all-stub
_TAG_EMPTY_FRAGMENT = "empty_fragment"
_TAG_EMPTY_ELEMENT = "empty_element"

# Map classification tag → rule_id when the body is an arrow expression-body.
_ARROW_TAG_TO_RULE = {
    _TAG_LITERAL: RULE_ARROW_LITERAL,
    _TAG_UNCONDITIONAL: RULE_UNCONDITIONAL_STUB,
    _TAG_EMPTY_FRAGMENT: RULE_EMPTY_FRAGMENT,
    _TAG_EMPTY_ELEMENT: RULE_EMPTY_ELEMENT,
}

# Map classification tag → rule_id when the body is a function block with a
# single stub return statement.
_BLOCK_TAG_TO_RULE = {
    _TAG_LITERAL: RULE_FN_RETURN_LITERAL,
    _TAG_UNCONDITIONAL: RULE_UNCONDITIONAL_STUB,
    _TAG_EMPTY_FRAGMENT: RULE_EMPTY_FRAGMENT,
    _TAG_EMPTY_ELEMENT: RULE_EMPTY_ELEMENT,
}

# Function-shaped node types that *terminate* return-statement collection.
# We must NOT descend into nested function scopes, otherwise a `return null`
# inside a closure would falsely flag the outer component.
_NESTED_FUNCTION_TYPES = {
    "function_declaration",
    "function_expression",
    "arrow_function",
    "method_definition",
    "generator_function",
    "generator_function_declaration",
}


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _strip_parens(node):
    """Return the innermost expression, peeling parenthesized_expression layers."""
    while node is not None and node.type == "parenthesized_expression":
        inner = next(
            (c for c in node.children if c.type not in ("(", ")")),
            None,
        )
        if inner is None:
            return node
        node = inner
    return node


def _classify_stub_expr(node, source: bytes) -> Optional[str]:
    """Return one of the ``_TAG_*`` constants if *node* is statically a stub.

    Recursive over ternary and parenthesized expressions: a ternary is a stub
    only if both branches are stubs. ``None`` means "not statically a stub".
    """
    if node is None:
        return _TAG_LITERAL  # bare ``return;`` collapses here
    node = _strip_parens(node)
    if node is None:
        return None

    t = node.type
    if t == "null":
        return _TAG_LITERAL
    if t == "undefined":
        return _TAG_LITERAL
    if t == "identifier":
        if _node_text(node, source) == "undefined":
            return _TAG_LITERAL
        return None

    if t == "ternary_expression":
        consequence = node.child_by_field_name("consequence")
        alternative = node.child_by_field_name("alternative")
        c_tag = _classify_stub_expr(consequence, source)
        a_tag = _classify_stub_expr(alternative, source)
        if c_tag is not None and a_tag is not None:
            return _TAG_UNCONDITIONAL
        return None

    if t == "jsx_self_closing_element":
        # Self-closing always has zero children. Stub iff it carries no
        # attribute-shaped children (jsx_attribute) and no spread expressions
        # (jsx_expression directly inside the tag).
        for c in node.children:
            if c.type in ("jsx_attribute", "jsx_expression"):
                return None
        return _TAG_EMPTY_ELEMENT

    if t == "jsx_element":
        opening = node.child_by_field_name("open_tag")
        opening_is_fragment = True
        opening_attrs = 0
        if opening is not None:
            for c in opening.children:
                if c.type in ("jsx_attribute", "jsx_expression"):
                    opening_attrs += 1
                if c.type in (
                    "identifier",
                    "nested_identifier",
                    "member_expression",
                    "jsx_namespace_name",
                    "type_identifier",
                ):
                    opening_is_fragment = False

        meaningful_children = []
        for c in node.children:
            if c.type in ("jsx_opening_element", "jsx_closing_element"):
                continue
            if c.type == "jsx_text":
                if _node_text(c, source).strip():
                    meaningful_children.append(c)
                continue
            meaningful_children.append(c)

        if meaningful_children or opening_attrs > 0:
            return None
        return _TAG_EMPTY_FRAGMENT if opening_is_fragment else _TAG_EMPTY_ELEMENT

    return None


def _collect_returns_in_block(block_node):
    """Yield every ``return_statement`` reachable inside *block_node*, refusing
    to descend into nested function scopes (closures keep their own returns).
    """
    stack = [block_node]
    while stack:
        n = stack.pop()
        for child in n.children:
            if child.type == "return_statement":
                yield child
                continue
            if child.type in _NESTED_FUNCTION_TYPES:
                # New function scope — its returns don't belong to the outer one.
                continue
            stack.append(child)


def _return_value(return_stmt):
    """Return the value expression of a ``return_statement`` (or None for bare ``return;``)."""
    for c in return_stmt.children:
        if c.type in ("return", ";"):
            continue
        return c
    return None


def _classify_block_returns(block_node, source: bytes) -> Optional[str]:
    """Classify a function block's returns. ``None`` means "not a stub"."""
    returns = list(_collect_returns_in_block(block_node))
    if not returns:
        # No return at all → implicit undefined fall-through. We treat this as
        # NOT a stub: the function may have side-effects (rare for components,
        # but flagging would be too aggressive).
        return None

    tags: List[str] = []
    for r in returns:
        val = _return_value(r)
        tag = _classify_stub_expr(val, source)
        if tag is None:
            return None  # at least one real return → not a stub
        tags.append(tag)

    # Pick the most specific tag: unconditional > empty_fragment > empty_element > literal.
    for preferred in (_TAG_UNCONDITIONAL, _TAG_EMPTY_FRAGMENT, _TAG_EMPTY_ELEMENT, _TAG_LITERAL):
        if preferred in tags:
            return preferred
    return None


def _is_component_name(name: str) -> bool:
    """Component identifiers are PascalCase. Lowercase identifiers are usually
    helpers, hooks (``useFoo``), or non-component utilities — out of scope.
    """
    return bool(name) and name[0].isupper()


def _iter_top_level_declarations(root):
    """Yield ``(name_node, function_like_node)`` pairs for module-level
    functional components — arrow assignments, function expressions, and
    function declarations. Class components are deferred (Decision #7 limits
    first-cut scope to functional TSX components).
    """
    for stmt in root.children:
        node = stmt
        if node.type == "export_statement":
            node = node.child_by_field_name("declaration") or node

        if node is None:
            continue

        if node.type == "lexical_declaration":
            for declarator in node.children:
                if declarator.type != "variable_declarator":
                    continue
                name_node = declarator.child_by_field_name("name")
                value = declarator.child_by_field_name("value")
                if name_node is None or value is None:
                    continue
                if value.type not in ("arrow_function", "function_expression"):
                    continue
                yield name_node, value
        elif node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                yield name_node, node


def _line_of(node, source: bytes) -> int:
    """1-based line number for a tree-sitter node (start point row is 0-based)."""
    return node.start_point[0] + 1


def _check_function_like(func_node, source: bytes) -> Optional[str]:
    """Classify a function-shaped node body. Returns the body classification tag."""
    if func_node.type == "arrow_function":
        body = func_node.child_by_field_name("body")
        if body is None:
            return None
        if body.type == "statement_block":
            return _classify_block_returns(body, source)
        return _classify_stub_expr(body, source)

    body = func_node.child_by_field_name("body")
    if body is None or body.type != "statement_block":
        return None
    return _classify_block_returns(body, source)


def detect_stub_returns(file_path: Path) -> List[Violation]:
    """Return ``Violation`` records for every stub-return component in *file_path*.

    Detection follows Decision #2 (tree-sitter AST). When tree-sitter is
    unavailable in the environment, returns an empty list — the validator
    is a no-op rather than a hard import failure for unconfigured consumers.
    """
    try:
        source = file_path.read_bytes()
    except OSError:
        return []

    tree = parse_tsx(source)
    if tree is None:
        return []  # parser unavailable; degrade gracefully

    try:
        rel = file_path.relative_to(REPO_ROOT)
    except ValueError:
        rel = file_path

    violations: List[Violation] = []
    for name_node, func_node in _iter_top_level_declarations(tree.root_node):
        name = _node_text(name_node, source)
        if not _is_component_name(name):
            continue

        # Arrow expression body needs the arrow-specific rule mapping; everything
        # else (function body) uses the block mapping.
        is_arrow_expr_body = (
            func_node.type == "arrow_function"
            and func_node.child_by_field_name("body") is not None
            and func_node.child_by_field_name("body").type != "statement_block"
        )

        if is_arrow_expr_body:
            body = func_node.child_by_field_name("body")
            tag = _classify_stub_expr(body, source)
            if tag is None:
                continue
            rule_id = _ARROW_TAG_TO_RULE[tag]
            line = _line_of(func_node, source)
        else:
            tag = _check_function_like(func_node, source)
            if tag is None:
                continue
            rule_id = _BLOCK_TAG_TO_RULE[tag]
            line = _line_of(func_node, source)

        violations.append(Violation(
            rule_id=rule_id,
            severity=STUB_RULE_SEVERITY,
            location=f"{rel}:{line}",
            detail=f"stub presentation return in component '{name}' ({tag})",
        ))

    return violations


# ---------------------------------------------------------------------------
# Scan helpers
# ---------------------------------------------------------------------------
def _scan_paths(
    scan_dirs: List[str],
    allowlist: Dict[str, str],
    repo_root: Path,
) -> Tuple[int, List[Violation]]:
    """Scan helper that takes config explicitly. Used by both production scans
    and SMOKE tests (which pass tmp roots and synthetic allowlists)."""
    files = _collect_tsx_files(scan_dirs, repo_root=repo_root)
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


def scan_stub_presentation_returns(repo_root: Path) -> Tuple[int, List[Violation]]:
    """Aggregate stub-return violations across configured scan_dirs."""
    cfg = _load_config()
    scan_dirs = cfg.get("scan_dirs", []) or []
    if not scan_dirs:
        return 0, []
    allowlist = _load_allowlist(cfg)
    return _scan_paths(scan_dirs, allowlist, repo_root)


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
def test_smoke_jel_app_repro_emits_arrow_literal_violation(tmp_path):
    """
    GT-030 SMOKE: the jel-app incident (#318) reproduces.

    Given: a tmp tree mirroring web/src/auth/presentation/AuthGateShell.tsx
           with the verbatim incident body
    When:  scan runs with no allowlist
    Then:  PRESENTATION-NOSTUB-001 is emitted at the expected location
    """
    pres_dir = tmp_path / "web" / "src" / "auth" / "presentation"
    pres_dir.mkdir(parents=True)
    target = pres_dir / "AuthGateShell.tsx"
    target.write_text("export const AuthGateShell = () => null;\n", encoding="utf-8")

    count, violations = _scan_paths(["web/src"], allowlist={}, repo_root=tmp_path)

    assert count == 1, f"Expected 1 violation, got {count}: {violations}"
    v = violations[0]
    assert v.rule_id == RULE_ARROW_LITERAL
    assert v.severity == STUB_RULE_SEVERITY
    assert v.location.endswith("AuthGateShell.tsx:1")


@pytest.mark.coder
def test_smoke_allowlist_round_trip_clears_violations(tmp_path):
    """
    GT-031 SMOKE: an allowlist entry with a migration ref clears the violation.

    Given: same tmp jel-app tree as GT-030
    When:  the file path is in the allowlist
    Then:  zero violations
    """
    pres_dir = tmp_path / "web" / "src" / "auth" / "presentation"
    pres_dir.mkdir(parents=True)
    target = pres_dir / "AuthGateShell.tsx"
    target.write_text("export const AuthGateShell = () => null;\n", encoding="utf-8")
    rel = str(target.relative_to(tmp_path))

    count, violations = _scan_paths(
        ["web/src"],
        allowlist={rel: "owner/repo#999"},
        repo_root=tmp_path,
    )
    assert count == 0, f"Allowlist did not clear violation: {violations}"


@pytest.mark.coder
def test_smoke_fixture_tree_is_excluded_from_scans(tmp_path):
    """
    SMOKE: the validator's own fixtures must never be scanned, even if a
    consumer accidentally points scan_dirs at the toolkit tree.

    Given: tmp tree containing fixtures/ and a stub TSX inside it
    When:  scan runs
    Then:  zero violations (path filter rejects /fixtures/)
    """
    fixt = tmp_path / "src" / "toolkit" / "fixtures" / "presentation"
    fixt.mkdir(parents=True)
    (fixt / "stub.tsx").write_text("export const X = () => null;\n", encoding="utf-8")

    count, violations = _scan_paths(["src"], allowlist={}, repo_root=tmp_path)
    assert count == 0, f"Fixture tree leaked into scan: {violations}"


@pytest.mark.coder
def test_smoke_atdd_self_scan_is_clean():
    """
    SMOKE: scanning the ATDD repo's own configured scan_dirs (per
    .atdd/config.yaml) yields zero violations. The toolkit has no production
    TSX, so an empty scan_dirs list keeps this a no-op pass; if a future
    contributor adds TSX, this test catches a regression at SMOKE time.
    """
    count, violations = scan_stub_presentation_returns(REPO_ROOT)
    assert count == 0, (
        f"Unexpected stub-presentation violations in ATDD self-scan:\n"
        + "\n".join(f"  {v}" for v in violations)
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

    frontend_block = convention.get("frontend") or {}
    block = frontend_block.get("no_stub_presentation") or {}
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
