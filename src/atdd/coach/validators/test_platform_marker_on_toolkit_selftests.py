# URN: component:govern-lifecycle:enforcement-substrate:test_platform_marker_on_toolkit_selftests:backend:domain
# Runtime: python
# Purpose: A shipped validator test that asserts on a toolkit-only path must carry the platform marker.

"""Close the toolkit-self-test leak class (#1475).

``atdd validate <phase>`` collects the validator directories of the *installed*
atdd package, so a consumer repo runs the toolkit's own shipped validators
against itself. The only mechanism that holds toolkit dogfood tests back is the
``platform`` marker: ``TestRunner.run_tests`` appends ``not platform`` to the
marker expression whenever ``is_atdd_source_repo()`` is False.

Nothing enforced that the marker was ever *applied*. So it wasn't — and five
tests asserting on ``find_repo_root() / "docs" / "smoke-audit.md"`` and
``find_repo_root() / "src" / "atdd" / ...`` failed in every consumer repo that
installed the wheel (#954, #1325, #1341). In the toolkit's own CI those paths
exist and the assertions are true, and the ``not platform`` exclusion only fires
when NOT in the source repo — so our suite runs a superset of a consumer's and
is always green. We are structurally incapable of seeing the failure. This
validator is the seeing.

Sibling rule ``coach.source-layout.no-toolkit-self-layout-assumption``
(COACH-PKG-LAYOUT-001) scans production code for the same path shape and
*exempts* tests — correctly, because a test may legitimately mean to assert on
the toolkit repo. For a test the remedy is not package-relative resolution but
exclusion from consumer sweeps, i.e. the marker. This rule is that complement.

Granularity is per test function, not per module: several validators mix
toolkit-self assertions with tests that genuinely gate the *consumer's* repo
(``test_subject_invariants.py`` holds both). Marking such a module wholesale
would silently disable a live gate — the same harm as moving the file out of
``validators/``. Mark the module only when every test in it is toolkit-self.

Suppression: ``# atdd:suppress(coach.source-layout.platform-marker-on-toolkit-selftest)``
on the offending line.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Optional

import pytest

import atdd
from atdd.coach.utils.rule_binding import bind_rule

_RULE = bind_rule("coach.source-layout.platform-marker-on-toolkit-selftest")

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
ARCHETYPES = ("planner", "tester", "coder", "coach")

SUPPRESSION_MARKER = "atdd:suppress(coach.source-layout.platform-marker-on-toolkit-selftest)"

# Path segments that exist in the toolkit checkout and can never exist in a
# consumer repo. `src/atdd` is the toolkit's own source; `docs` and
# `.github/workflows` are its repo-hygiene surfaces. A consumer's own `src/` or
# `docs/` is not implicated — only these exact toolkit-owned prefixes are.
TOOLKIT_ONLY_PREFIXES = ("src/atdd", "docs", ".github")

# `Path(__file__).resolve().parents[N]`: for a validator at
# src/atdd/<archetype>/validators/x.py the package boundary is parents[2] (=atdd).
# Anything at or beyond parents[3] reaches for `src/` or the repo root — which in
# a wheel install is site-packages, i.e. meaningless. Such a test is asking for
# the toolkit checkout.
_PARENTS_ESCAPES_PACKAGE = 3


def _iter_validator_test_files() -> List[Path]:
    """Every shipped validator test file, including those in tests/ subdirs."""
    files: List[Path] = []
    for archetype in ARCHETYPES:
        root = ATDD_PKG_DIR / archetype / "validators"
        if not root.is_dir():
            continue
        for path in root.rglob("test_*.py"):
            if "fixtures" in path.parts or "__pycache__" in path.parts:
                continue
            files.append(path)
    return sorted(files)


def _div_chain_operands(node: ast.AST) -> List[ast.AST]:
    """Flatten a left-deep ``a / b / c`` BinOp chain into its operands."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _div_chain_operands(node.left) + [node.right]
    return [node]


def _calls_find_repo_root(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "find_repo_root":
            return True
        if isinstance(func, ast.Name) and func.id == "Path" and len(node.args) == 1:
            return _calls_find_repo_root(node.args[0])
    if isinstance(node, ast.BoolOp):
        return any(_calls_find_repo_root(v) for v in node.values)
    return False


def _parents_index(node: ast.AST) -> Optional[int]:
    """``<expr>.parents[N]`` → N, else None."""
    if not isinstance(node, ast.Subscript):
        return None
    value = node.value
    if not (isinstance(value, ast.Attribute) and value.attr == "parents"):
        return None
    idx = node.slice
    if isinstance(idx, ast.Constant) and isinstance(idx.value, int):
        return idx.value
    return None


def _descends_into_toolkit_only(operands: List[ast.AST]) -> bool:
    """True iff the string segments after the chain head name a toolkit-only dir."""
    segments = "/".join(
        op.value.strip("/")
        for op in operands[1:]
        if isinstance(op, ast.Constant) and isinstance(op.value, str)
    )
    return any(
        segments == p or segments.startswith(p + "/") for p in TOOLKIT_ONLY_PREFIXES
    )


def _reaches_toolkit_only_path(node: ast.AST, root_names: set, toolkit_names: set) -> bool:
    """True iff *node* builds a path only the toolkit checkout can satisfy.

    Deliberately NOT true of a bare ``find_repo_root()``: in a consumer that is
    the consumer's own root, and the validators that scan it (dead code,
    hardcoded secrets, plan/ wagon themes, ...) are exactly the live gates we
    must not disable. Only *descent into* a toolkit-owned directory — or a
    ``parents[N]`` walk, which resolves to site-packages in a wheel and is
    therefore already broken — makes a path toolkit-only.
    """
    # Shape 1: <repo-root> / "src" / "atdd" / ...  where <repo-root> is either a
    # direct find_repo_root() call or a module name already bound to one.
    operands = _div_chain_operands(node)
    if len(operands) > 1:
        head = operands[0]
        head_is_root = _calls_find_repo_root(head) or (
            isinstance(head, ast.Name) and head.id in root_names
        )
        if head_is_root and _descends_into_toolkit_only(operands):
            return True
        # Descent from a name already known to be toolkit-only stays toolkit-only.
        if isinstance(head, ast.Name) and head.id in toolkit_names:
            return True

    # Shape 2: Path(__file__).resolve().parents[N] reaching past the atdd package.
    for sub in ast.walk(node):
        idx = _parents_index(sub)
        if idx is not None and idx >= _PARENTS_ESCAPES_PACKAGE:
            return True
    return False


def _module_has_platform_marker(tree: ast.Module) -> bool:
    """``pytestmark = [... pytest.mark.platform ...]`` at module level."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
        ):
            continue
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Attribute) and sub.attr == "platform":
                return True
    return False


def _function_has_platform_marker(fn: ast.FunctionDef) -> bool:
    for dec in fn.decorator_list:
        for sub in ast.walk(dec):
            if isinstance(sub, ast.Attribute) and sub.attr == "platform":
                return True
    return False


def _names_referenced(node: ast.AST) -> set:
    return {sub.id for sub in ast.walk(node) if isinstance(sub, ast.Name)}


def _analyse_module(tree: ast.Module) -> tuple:
    """Fixpoint over module scope → (toolkit_names, toolkit_helpers).

    Toolkit-only-ness reaches a test through two layers of indirection, and the
    first cut of this validator missed both:

        REPO_ROOT = find_repo_root()                  # benign on its own
        WORKFLOW  = REPO_ROOT / ".github" / "wf.yml"  # toolkit-only, via a NAME
        def scan(): return NODES.glob(...)            # toolkit-only, via a HELPER
        def test_x(): assert_ok(scan())               # names neither directly

    So propagate to a fixpoint: a name assigned from a toolkit-only expression
    is toolkit-only; a module-level function that touches a toolkit-only name
    (or calls a function that does) carries it to any test that calls it.
    """
    root_names: set = set()
    toolkit_names: set = set()

    for node in tree.body:
        if isinstance(node, ast.Assign) and _calls_find_repo_root(node.value):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    root_names.add(t.id)

    # Assignments: iterate, since a later name may depend on an earlier one.
    changed = True
    while changed:
        changed = False
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if targets <= toolkit_names:
                continue
            if _reaches_toolkit_only_path(node.value, root_names, toolkit_names) or (
                _names_referenced(node.value) & toolkit_names
            ):
                toolkit_names |= targets
                changed = True

    # Helper functions that carry a toolkit-only path to their callers.
    helpers = {
        n.name: n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and not n.name.startswith("test_")
    }
    toolkit_helpers: set = set()
    changed = True
    while changed:
        changed = False
        for name, fn in helpers.items():
            if name in toolkit_helpers:
                continue
            refs = _names_referenced(fn)
            inline = any(
                _reaches_toolkit_only_path(sub, root_names, toolkit_names)
                for sub in ast.walk(fn)
                if isinstance(sub, (ast.BinOp, ast.Subscript))
            )
            if inline or (refs & toolkit_names) or (refs & toolkit_helpers):
                toolkit_helpers.add(name)
                changed = True

    return toolkit_names, toolkit_helpers


def _is_suppressed(fn: ast.FunctionDef, source_lines: List[str]) -> bool:
    start = fn.lineno - 1
    end = min(getattr(fn, "end_lineno", fn.lineno), len(source_lines))
    return any(SUPPRESSION_MARKER in source_lines[i] for i in range(start, end))


def _scan_file(path: Path) -> List[str]:
    """Return one message per unmarked toolkit-self test in *path*."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    source_lines = source.splitlines()
    if _module_has_platform_marker(tree):
        return []

    toolkit_names, toolkit_helpers = _analyse_module(tree)
    root_names = {
        t.id
        for node in tree.body
        if isinstance(node, ast.Assign) and _calls_find_repo_root(node.value)
        for t in node.targets
        if isinstance(t, ast.Name)
    }
    violations: List[str] = []

    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or not fn.name.startswith("test_"):
            continue
        if _function_has_platform_marker(fn) or _is_suppressed(fn, source_lines):
            continue

        # Toolkit-self if the body builds such a path inline, reads a name bound
        # to one, or calls a helper that does either.
        refs = _names_referenced(fn)
        inline = any(
            _reaches_toolkit_only_path(sub, root_names, toolkit_names)
            for sub in ast.walk(fn)
            if isinstance(sub, (ast.BinOp, ast.Subscript))
        )
        if inline or (refs & toolkit_names) or (refs & toolkit_helpers):
            violations.append(f"{path.name}::{fn.name} (line {fn.lineno})")

    return violations


@pytest.mark.coach
def test_no_unmarked_toolkit_selftests() -> None:
    """Every shipped validator test asserting on a toolkit-only path is platform-marked.

    An unmarked one runs in every consumer sweep and fails there with no
    consumer-side fix: the path it asserts on belongs to the toolkit checkout.
    """
    violations: List[str] = []
    for path in _iter_validator_test_files():
        violations.extend(_scan_file(path))

    assert not violations, (
        f"[{_RULE.rule_id}] {len(violations)} shipped validator test(s) assert on a "
        "toolkit-only path without pytest.mark.platform.\n"
        "Each one runs inside every consumer repo and fails there with no "
        "consumer-side fix — find_repo_root() resolves to the CONSUMER's root, "
        "where src/atdd and docs/ can never exist.\n\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nFix: add pytest.mark.platform — to the module's pytestmark if every "
        "test in it is toolkit-self, or to the individual test function if the "
        "module also holds tests that gate the consumer's own repo.\n"
        "Do NOT move the file out of validators/: validators are collected by "
        "directory, so relocating one silently disables it as a live gate."
    )
