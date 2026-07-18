# URN: component:govern-lifecycle:enforcement-substrate:test_code_roots_agnosticity:backend:domain
# Runtime: python
# Purpose: Enforce the code-roots agnosticity invariant across core — no toolkit-layout hardcodes (issue #1499).

"""Code-roots agnosticity enforcement (issue #1499).

``code-roots.convention.yaml`` has stated the right invariant since #327:
roots are *declared* (``.atdd/config.yaml::code``) and *handed to* resolvers,
never frozen into source. Until this validator the convention was 100 lines of
prose with no ``rules:`` block, no disposition and no binding — every hardcode
violated it on paper and landed anyway (#1476: "implementation-root-resolution
is documentation-only and gates nothing").

atdd dogfoods itself: the atdd repo is just another CONSUMER of its own
toolkit. So a toolkit-layout hardcode is not a style nit — it breaks the
toolkit for every consumer, where core ships as an installed package and
``<repo>/src/atdd`` does not exist. Agnosticity is a correctness invariant.

Three rules, each grounded in a defect present in the tree today:

``coach.code-roots.no-hardcoded-toolkit-root``
    Literal toolkit-layout segments (``"src" / "atdd"``) joined onto a real
    repository root. Works in toolkit-self, resolves to a non-existent path in
    every pip-installed consumer.

``coach.code-roots.no-source-depth-walk``
    ``Path(__file__).parent`` chains deep enough to climb out of the package.
    They encode source-tree depth, which differs in site-packages.

``coach.code-roots.resolver-degrades-not-raises``
    Root resolution that *raises* when the root is absent. The convention's
    resolver contract already mandates the opposite: "return an empty list
    (not raise) when root does not exist". Absence of a subject is a fact to
    skip on, never to crash on.

Scope: the whole ``src/atdd`` tree — coach, coder, planner, tester, state,
cli. No archetype is exempt. The rule is toolkit-self (it governs *core's*
source), so the scan no-ops in a consumer repo, where core is an installed
package the consumer cannot edit.

Discrimination — why this is not the next ``dead-code.reachability``:

  * Exclusion is by DIRECTORY (``tests/``, ``fixtures/``), never by filename.
    Files named ``test_*.py`` sitting directly in ``*/validators/`` are
    production validators, not tests — that is exactly where the #1341 class
    of defect lives, so they stay in scope.
  * The toolkit-root rule is DEFAULT-DENY on its base expression: it fires
    only when the literal segments hang off a known repo-root vocabulary.
    ``tmp_path / "src" / "atdd"`` (a synthetic tree) is structurally
    unflaggable because ``tmp_path`` is not repo-root-ish.
  * Package-relative resolution is the CORRECT pattern and is never flagged.
    The depth rule's boundary is computed PER FILE — a chain is a defect only
    when it climbs above the atdd package root, which is what actually breaks
    in site-packages. A 3-chain in ``atdd/coach/validators/x.py`` lands on the
    package root and is fine; the same 3-chain in ``atdd/cli.py`` escapes.
    ``importlib.resources`` is not a path-arithmetic shape at all.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Optional, Set, Tuple

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation


# `platform` is what excludes this from consumer sweeps: the audit reaches for
# find_repo_root()/src/atdd, which in a consumer repo resolves to *their* root
# where it can never exist. The skip in the tests is a fallback; the marker is
# the contract (coach.source-layout.platform-marker-on-toolkit-selftest).
pytestmark = [pytest.mark.coach, pytest.mark.platform]


# Module-level binding is the contract (SPEC-COACH-RULEID-0007): the reverse-
# coherence gate resolves each node's `implementation.ref` back to this module
# and requires a literal bind_rule call for the rule it names.
_RULE_TOOLKIT_ROOT = bind_rule("coach.code-roots.no-hardcoded-toolkit-root")
_RULE_DEPTH_WALK = bind_rule("coach.code-roots.no-source-depth-walk")
_RULE_DEGRADES = bind_rule("coach.code-roots.resolver-degrades-not-raises")


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------
# Names that denote a REAL repository root. Joining toolkit-layout segments
# onto one of these is the hardcode. Anything outside this set — `tmp_path`,
# `fixture_root`, a synthetic checkout under a temp dir — is not a repo root
# and is structurally excluded. Default-deny is the point: the detector must
# prove the base is a repo root before it fires.
_REPO_ROOT_NAMES = {
    "REPO_ROOT",
    "_REPO_ROOT",
    "REPO",
    "_REPO",
    "ROOT",
    "_ROOT",
    "repo_root",
    "_repo_root",
    "repo",
    "root",
    "PROJECT_ROOT",
    "project_root",
    "WORKTREE_ROOT",
    "worktree_root",
}
_REPO_ROOT_CALLS = {"find_repo_root", "get_repo_root"}

# Toolkit-layout segments. `src/atdd` is the source-checkout shape; it is
# precisely what does NOT exist once atdd is installed as a package.
_TOOLKIT_SEGMENTS = ("src", "atdd")

# A `.parent` chain is only a defect when it climbs ABOVE the package root —
# that is what encodes SOURCE-TREE depth and lands somewhere else once
# installed. A chain that stops at or inside the package is package-relative
# and is correct in a checkout AND in site-packages.
#
# The boundary is per-file, not a flat number. For a module `atdd/a/b/c.py`
# (relative parts = 3), `Path(__file__).parent` is `atdd/a/b`, so:
#
#     chain 3  -> atdd/          the package root — CORRECT, equivalent to
#                                Path(atdd.__file__).parent
#     chain 4  -> src/           ABOVE the package — breaks in site-packages,
#                                where there is no `src/`
#
# So the chain escapes exactly when `chain > len(relative.parts)`. A flat
# threshold gets this wrong in both directions: it clears a 2-chain in
# `atdd/cli.py` (which already escapes) and flags a 3-chain in
# `atdd/coach/validators/x.py` (which is just the package root).
def _max_package_relative_chain(location: str) -> int:
    """Longest ``.parent`` chain from *location* that stays inside the package."""
    return len(Path(location).parts)


# ---------------------------------------------------------------------------
# Structural exemptions
# ---------------------------------------------------------------------------
# None of these is a suppression. Each is a place where the pattern is not a
# consumer-breaking hardcode:
#
#   coach/utils/config.py       — the declaration surface itself. It owns
#                                 DEFAULT_CODE_ROOTS; the maps have to name a
#                                 concrete path somewhere or there is no
#                                 default to resolve. This is the one module
#                                 the convention exists to concentrate.
#   coder/validators/_toolkit_roots.py
#                               — the sanctioned toolkit-root resolver
#                                 (#1476/#1485). It is the approved
#                                 implementation of the very lookup this rule
#                                 forces everyone else to route through.
#   this module                 — it carries the literal segments as detector
#                                 vocabulary.
_EXEMPT_FILES = {
    Path("coach") / "utils" / "config.py",
    Path("coder") / "validators" / "_toolkit_roots.py",
    Path("coach") / "validators" / "test_code_roots_agnosticity.py",
}

# Directory-scoped exclusions. `tests/` and `fixtures/` hold synthetic trees
# built to be walked by other validators — they need literal paths to build
# the tree, and their roots are temp dirs, not this repo. Excluding by
# DIRECTORY (not by `test_*.py` filename) is deliberate: a `test_*.py` file
# sitting directly in `*/validators/` is a production validator and stays in
# scope.
_EXEMPT_DIR_NAMES = {"tests", "test", "fixtures", "__pycache__"}

# Synthetic-tree builders. `validators/conventions/<family>/fixtures.py` seeds a
# throwaway checkout under a temp dir for the convention suite to evaluate — it
# has to spell `root / "src" / "atdd" / ...` to BUILD the tree, and its `root`
# is a tmp_path, not this repository. Same category as a `fixtures/` directory;
# only the layout convention differs (module, not package).
_EXEMPT_FILE_NAMES = {"fixtures.py", "conftest.py"}


def _is_exempt(relative: Path) -> bool:
    """True when *relative* (a path under ``src/atdd``) is out of scope."""
    if relative in _EXEMPT_FILES:
        return True
    if relative.name in _EXEMPT_FILE_NAMES:
        return True
    return bool(_EXEMPT_DIR_NAMES.intersection(relative.parts))


def _suppression_marker(rule_id: str) -> str:
    return f"atdd:suppress({rule_id})"


def _is_suppressed(node: ast.AST, source_lines: List[str], rule_id: str) -> bool:
    """True when an inline pragma silences *rule_id* on *node*'s line range.

    The `suppress-and-clean` disposition needs a per-site opt-out so the
    pre-existing violations are visible AT their site and greppable — a count
    baseline would let an author add one violation while deleting another and
    stay green. Suppressions may only be removed; the destination is `strict`
    at zero.
    """
    marker = _suppression_marker(rule_id)
    start = getattr(node, "lineno", None)
    if start is None:
        return False
    end = getattr(node, "end_lineno", None) or start
    for lineno in range(start, end + 1):
        index = lineno - 1
        if 0 <= index < len(source_lines) and marker in source_lines[index]:
            return True
    return False


# ---------------------------------------------------------------------------
# Shared AST helpers
# ---------------------------------------------------------------------------
def _div_chain_operands(node: ast.AST) -> List[ast.AST]:
    """Flatten a left-deep ``a / b / c`` chain into its operands, in order."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _div_chain_operands(node.left) + [node.right]
    return [node]


def _is_outermost_div(node: ast.BinOp, tree: ast.AST) -> bool:
    """True when *node* is not the left operand of an enclosing ``/`` BinOp.

    Only the outermost link of a chain is a distinct site: reporting the inner
    ``ROOT / "src"`` of ``ROOT / "src" / "atdd"`` separately would double-count
    one hardcode and obscure which path was actually meant.
    """
    for outer in ast.walk(tree):
        if (
            isinstance(outer, ast.BinOp)
            and isinstance(outer.op, ast.Div)
            and outer.left is node
        ):
            return False
    return True


def _unwrap(node: ast.AST) -> ast.AST:
    """Peel ``Path(x)`` / ``str(x)`` / ``(a or b)`` wrappers off *node*."""
    if isinstance(node, ast.Call):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in {"Path", "str"} and len(node.args) == 1:
            return _unwrap(node.args[0])
    if isinstance(node, ast.BoolOp) and node.values:
        # `x or find_repo_root()` — the fallback carries the meaning.
        return _unwrap(node.values[-1])
    return node


def _denotes_repo_root(node: ast.AST) -> bool:
    """True when *node* evaluates to a real repository root.

    This is the false-positive control for the toolkit-root rule. A base the
    detector cannot positively identify as a repo root is not flagged.
    """
    inner = _unwrap(node)
    if isinstance(inner, ast.Name):
        return inner.id in _REPO_ROOT_NAMES
    if isinstance(inner, ast.Attribute):
        return inner.attr in _REPO_ROOT_NAMES
    if isinstance(inner, ast.Call):
        func = inner.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        return name in _REPO_ROOT_CALLS
    return False


def _literal_segments(operands: List[ast.AST]) -> List[str]:
    """String-literal operands of a chain, split on ``/``.

    ``["src", "atdd"]`` for both ``ROOT / "src" / "atdd"`` and
    ``ROOT / "src/atdd"`` — the two spellings are one shape.
    """
    parts: List[str] = []
    for operand in operands:
        if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
            parts.extend(p for p in operand.value.strip("/").split("/") if p)
    return parts


def _contains_toolkit_layout(segments: List[str]) -> bool:
    """True when ``src`` is immediately followed by ``atdd`` in *segments*."""
    for i in range(len(segments) - 1):
        if (segments[i], segments[i + 1]) == _TOOLKIT_SEGMENTS:
            return True
    return False


def _expr(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except (AttributeError, ValueError):
        return "<unparsable>"


# ---------------------------------------------------------------------------
# Rule 1 — no-hardcoded-toolkit-root
# ---------------------------------------------------------------------------
# Markers of the SANCTIONED dual-resolution idiom. Core legitimately resolves a
# package resource package-relatively and falls back to the source checkout, or
# resolves `<root>/src/atdd` and degrades when it is absent:
#
#     src = Path(repo_root) / "src" / "atdd"
#     if not src.is_dir():
#         return ids                      # <- degrades, agnostic
#
#     _CONVENTION_ROOTS = [ATDD_PKG_DIR,   # <- package-relative primary
#                          find_repo_root() / "src" / "atdd"]   # checkout fallback
#
# That is the shape the convention ASKS for ("skip on absence-of-SUBJECT"), so a
# scope carrying either marker is not flagged. This is deliberately biased
# toward under-firing: the defect this rule exists to catch is source that
# ASSUMES the checkout is there, and a rule nobody trusts is worse than no rule
# (see coder.dead-code.reachability, 362 false positives, universally ignored).
_GUARD_ATTRS = {"is_dir", "exists", "is_file"}
_PACKAGE_RELATIVE_MARKERS = {"ATDD_PKG_DIR", "__file__"}


def _scope_is_guarded(scope: ast.AST) -> bool:
    """True when *scope* existence-checks its paths or anchors package-relatively."""
    for node in ast.walk(scope):
        if isinstance(node, ast.Attribute) and node.attr in _GUARD_ATTRS:
            return True
        if isinstance(node, ast.Name) and node.id in _PACKAGE_RELATIVE_MARKERS:
            return True
    return False


# Signals that a scope BUILDS a synthetic tree rather than reading this repo.
# A helper that mkdir()s or write_text()s under its `root` argument is seeding a
# throwaway checkout for another validator to walk — it must spell the literal
# layout to create it, and its `root` is a temp dir:
#
#     def _make_atdd_checkout(root: Path) -> None:
#         (root / "src" / "atdd" / "coach" / "validators").mkdir(parents=True)
#
# Same category as `fixtures/`; the parameter simply happens to be named `root`.
# `tmp_path` in scope is the pytest tell for the same thing.
_TREE_BUILDING_ATTRS = {"mkdir", "write_text", "write_bytes", "touch", "makedirs"}
_SYNTHETIC_ROOT_NAMES = {"tmp_path", "tmpdir", "tmp_path_factory"}


def _builds_synthetic_tree(scope: ast.AST) -> bool:
    """True when *scope* creates a tree rather than reading this repository."""
    for node in ast.walk(scope):
        if isinstance(node, ast.Attribute) and node.attr in _TREE_BUILDING_ATTRS:
            return True
        if isinstance(node, ast.Name) and node.id in _SYNTHETIC_ROOT_NAMES:
            return True
        if isinstance(node, ast.arg) and node.arg in _SYNTHETIC_ROOT_NAMES:
            return True
    return False


def _is_path_constructor(scope: ast.AST, node: ast.AST) -> bool:
    """True when *scope* merely RETURNS the path *node* builds.

    A helper whose body is ``return <root> / "src" / "atdd" / ...`` is a path
    CONSTRUCTOR, not a resolver — it hands a path back and the caller decides
    what absence means:

        def _repo_nodes_dir(root):                 # constructor (not flagged)
            return Path(root) / "src" / "atdd" / "planner" / "conventions" / "nodes"

        def _nodes_dirs(root):                     # resolver — owns the guard
            repo = _repo_nodes_dir(root)
            if repo.is_dir():                      # <- degrades here
                dirs.append(repo)

    Flagging the constructor would push authors to inline the path at every
    callsite, which is strictly worse. The obligation to degrade sits with the
    scope that USES the path, and that scope is checked independently.
    """
    if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for stmt in ast.walk(scope):
        if isinstance(stmt, ast.Return) and stmt.value is not None:
            if any(inner is node for inner in ast.walk(stmt.value)):
                return True
    return False


def _enclosing_scopes(tree: ast.AST) -> List[Tuple[ast.AST, Set[int]]]:
    """Each function scope in *tree* paired with the ids of the nodes it holds."""
    scopes: List[Tuple[ast.AST, Set[int]]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scopes.append((node, {id(n) for n in ast.walk(node)}))
    return scopes


def find_hardcoded_toolkit_roots(
    tree: ast.AST, source_lines: List[str], location: str
) -> List[Violation]:
    """Flag every UNGUARDED repo-root-anchored ``src/atdd`` path in *tree*."""
    violations: List[Violation] = []
    scopes = _enclosing_scopes(tree)
    module_guarded = _scope_is_guarded(tree)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
            continue
        if not _is_outermost_div(node, tree):
            continue
        operands = _div_chain_operands(node)
        if not operands or not _denotes_repo_root(operands[0]):
            continue
        if not _contains_toolkit_layout(_literal_segments(operands[1:])):
            continue
        if _is_suppressed(node, source_lines, _RULE_TOOLKIT_ROOT.rule_id):
            continue
        # Compliant when the nearest enclosing scope degrades on absence or
        # anchors package-relatively. Module scope is the fallback for
        # module-level constants.
        enclosing = [scope for scope, members in scopes if id(node) in members]
        if enclosing and (
            _scope_is_guarded(enclosing[-1])
            or _is_path_constructor(enclosing[-1], node)
            or _builds_synthetic_tree(enclosing[-1])
        ):
            continue
        if not enclosing and module_guarded:
            continue
        violations.append(
            Violation(
                rule_id=_RULE_TOOLKIT_ROOT.rule_id,
                severity=_RULE_TOOLKIT_ROOT.severity,
                location=f"{location}:{node.lineno}",
                detail=(
                    f"toolkit layout 'src/atdd' is hardcoded against the repo "
                    f"root: {_expr(node)}. That path does not exist once atdd "
                    f"is installed as a package. Resolve the toolkit root "
                    f"package-relatively instead — Path(atdd.__file__).resolve()"
                    f".parent — or declare it under .atdd/config.yaml::code and "
                    f"skip the stack when it is undeclared."
                ),
            )
        )
    return violations


# ---------------------------------------------------------------------------
# Rule 2 — no-source-depth-walk
# ---------------------------------------------------------------------------
def _parent_chain_depth(node: ast.Attribute) -> Tuple[int, ast.AST]:
    """Return ``(chain_length, base)`` for a ``x.parent.parent...`` chain."""
    depth = 0
    current: ast.AST = node
    while isinstance(current, ast.Attribute) and current.attr == "parent":
        depth += 1
        current = current.value
    return depth, current


def _is_file_anchored(node: ast.AST) -> bool:
    """True when *node* bottoms out at ``__file__`` (optionally ``.resolve()``).

    Requiring a ``__file__`` anchor is what keeps this rule narrow: it fires on
    source-tree depth walks, not on arbitrary ``some_dir.parent.parent``
    arithmetic over a path the caller was handed.
    """
    current = node
    while True:
        if isinstance(current, ast.Call):
            func = current.func
            if isinstance(func, ast.Attribute) and func.attr in {"resolve", "absolute"}:
                current = func.value
                continue
            name = getattr(func, "id", "")
            if name in {"Path", "str"} and current.args:
                current = current.args[0]
                continue
            return False
        if isinstance(current, ast.Name):
            return current.id == "__file__"
        return False


def find_source_depth_walks(
    tree: ast.AST, source_lines: List[str], location: str
) -> List[Violation]:
    """Flag every ``__file__``-anchored parent chain at or past the threshold."""
    violations: List[Violation] = []
    seen: Set[int] = set()
    escapes_at = _max_package_relative_chain(location)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and node.attr == "parent"):
            continue
        depth, base = _parent_chain_depth(node)
        if depth <= escapes_at or not _is_file_anchored(base):
            continue
        # Only the longest chain is a site: `a.parent.parent.parent` contains
        # shorter Attribute nodes that are links of the same walk.
        if id(base) in seen:
            continue
        seen.add(id(base))
        if _is_suppressed(node, source_lines, _RULE_DEPTH_WALK.rule_id):
            continue
        violations.append(
            Violation(
                rule_id=_RULE_DEPTH_WALK.rule_id,
                severity=_RULE_DEPTH_WALK.severity,
                location=f"{location}:{node.lineno}",
                detail=(
                    f"{_expr(node)} climbs {depth} levels from __file__, escaping "
                    f"the atdd package (this module tops out at {escapes_at}). "
                    f"That encodes source-tree depth: there is no `src/` once "
                    f"atdd is installed, so the chain lands somewhere else "
                    f"entirely. Anchor package resources "
                    f"package-relatively (Path(atdd.__file__).resolve().parent) "
                    f"or resolve the repo root with find_repo_root()."
                ),
            )
        )
    return violations


# ---------------------------------------------------------------------------
# Rule 3 — resolver-degrades-not-raises
# ---------------------------------------------------------------------------
def _iterates_ancestors(node: ast.For) -> bool:
    """True when *node* loops over a path's ancestors.

    Covers ``for d in start.parents:`` and the common
    ``for d in (start, *start.parents):`` spelling.
    """
    for inner in ast.walk(node.iter):
        if isinstance(inner, ast.Attribute) and inner.attr == "parents":
            return True
    return False


def _fallthrough_raises(func: ast.AST) -> List[ast.Raise]:
    """``raise`` statements that are the fall-through of an ancestor walk.

    This is the narrow shape the convention actually forbids: a resolver
    searches upward for a marker and, having failed to find one, crashes
    instead of returning None. The raise must be either the loop's ``else``
    body or a statement following the loop in the same block.

    Deliberately NOT flagged, because they are not resolution-failure policy:

      * guard clauses and input validation (``raise AuthorInputError(...)``
        because an argument was malformed) — a caller error, not an absent
        root;
      * ``raise`` inside an ``except`` handler — error translation;
      * any raise in a function that never walks ancestors at all.

    Rule 3 was measured against the tree before this narrowing: the loose
    "function mentions .parent anywhere" form produced 34 hits, the majority
    of them input validation. Precision beats reach — a rule nobody trusts is
    worse than no rule.
    """
    found: List[ast.Raise] = []
    for node in ast.walk(func):
        body = getattr(node, "body", None)
        blocks = [b for b in (body, getattr(node, "orelse", None)) if isinstance(b, list)]
        for block in blocks:
            for index, stmt in enumerate(block):
                if not (isinstance(stmt, ast.For) and _iterates_ancestors(stmt)):
                    continue
                # The loop's own `else:` body.
                for inner in stmt.orelse:
                    if isinstance(inner, ast.Raise):
                        found.append(inner)
                # The statement that follows the loop in the same block.
                if index + 1 < len(block) and isinstance(block[index + 1], ast.Raise):
                    found.append(block[index + 1])
    return found


def find_raising_resolvers(
    tree: ast.AST, source_lines: List[str], location: str
) -> List[Violation]:
    """Flag root-resolution helpers that raise instead of degrading."""
    violations: List[Violation] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for raise_node in _fallthrough_raises(func):
            if _is_suppressed(raise_node, source_lines, _RULE_DEGRADES.rule_id):
                continue
            violations.append(
                Violation(
                    rule_id=_RULE_DEGRADES.rule_id,
                    severity=_RULE_DEGRADES.severity,
                    location=f"{location}:{raise_node.lineno}",
                    detail=(
                        f"root resolver {func.name!r} raises when the root is "
                        f"absent ({_expr(raise_node)}). The resolver contract "
                        f"is to degrade, not crash: return None (or an empty "
                        f"list) so the caller can skip a stack this repo does "
                        f"not have. Absence of a subject is a fact to skip on, "
                        f"never a reason to fail."
                    ),
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------
def scan_source(source: str, location: str) -> List[Violation]:
    """Run all three detectors over one module's *source*."""
    try:
        tree = ast.parse(source, filename=location)
    except SyntaxError:
        # Unparseable core source is somebody else's failure to report.
        return []
    source_lines = source.splitlines()
    return (
        find_hardcoded_toolkit_roots(tree, source_lines, location)
        + find_source_depth_walks(tree, source_lines, location)
        + find_raising_resolvers(tree, source_lines, location)
    )


def scan_core_source(core_root: Path) -> List[Violation]:
    """Walk *core_root* and collect every code-roots violation."""
    violations: List[Violation] = []
    for path in sorted(core_root.rglob("*.py")):
        relative = path.relative_to(core_root)
        if _is_exempt(relative):
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        violations.extend(scan_source(source, str(relative)))
    return violations


def core_source_root() -> Optional[Path]:
    """The toolkit's own source tree, or None when core is installed."""
    candidate = find_repo_root() / "src" / "atdd"  # atdd:suppress(coach.code-roots.no-hardcoded-toolkit-root)
    return candidate if candidate.is_dir() else None


__all__ = [
    "core_source_root",
    "find_hardcoded_toolkit_roots",
    "find_raising_resolvers",
    "find_source_depth_walks",
    "scan_core_source",
    "scan_source",
]


# ===========================================================================
# Fault injection — each rule is proven to FAIL on the shape it forbids and to
# STAY SILENT on the compliant shape. A gate that cannot fail is a stub; a gate
# that fires on the fix pushes the next author back to the anti-pattern.
# ===========================================================================
_FAULT_TOOLKIT_ROOT = '''
from pathlib import Path
from atdd.coach.utils.repo import find_repo_root

def load_nodes():
    nodes = find_repo_root() / "src" / "atdd" / "coach" / "conventions" / "nodes"
    return sorted(nodes.rglob("*.convention.yaml"))
'''

_CLEAN_TOOLKIT_ROOT = '''
from pathlib import Path
import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent

def load_nodes():
    """Package-relative — correct in a checkout AND in site-packages."""
    return sorted((ATDD_PKG_DIR / "coach" / "conventions" / "nodes").rglob("*.yaml"))

def load_synthetic(tmp_path):
    """Synthetic tree: the base is not a repo root."""
    return tmp_path / "src" / "atdd" / "demo"

def seed(root):
    """Tree BUILDER — spells the layout to create it."""
    (root / "src" / "atdd" / "demo").mkdir(parents=True)

def degrading(repo_root):
    """Resolves the checkout but degrades when it is absent."""
    src = repo_root / "src" / "atdd"
    if not src.is_dir():
        return []
    return list(src.rglob("*.py"))
'''

# Evaluated as if it lived at `coach/validators/sample.py` (3 parts), so a
# chain of 3 reaches the package root and a chain of 5 escapes to the repo.
_SAMPLE_LOCATION = "coach/validators/sample.py"

_FAULT_DEPTH_WALK = '''
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
'''

_CLEAN_DEPTH_WALK = '''
from pathlib import Path
import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
PACKAGE_DIR = Path(__file__).resolve().parent
PARENT_PKG = Path(__file__).resolve().parent.parent
# Exactly the package root — the package-relative equivalent, NOT a defect.
PKG_ROOT = Path(__file__).resolve().parent.parent.parent
'''

_FAULT_DEGRADES = '''
from pathlib import Path

def find_root():
    here = Path(__file__).resolve()
    for anc in (here, *here.parents):
        if (anc / "plan").is_dir():
            return anc
    raise RuntimeError(f"could not locate repo root from {here}")
'''

_CLEAN_DEGRADES = '''
from pathlib import Path

def find_root():
    """Degrades: absence of the subject is a fact to skip on."""
    here = Path(__file__).resolve()
    for anc in (here, *here.parents):
        if (anc / "plan").is_dir():
            return anc
    return None

def validate(path):
    """Input validation is NOT a resolution-failure policy."""
    if path.parent.name not in ("nodes", "conventions"):
        raise ValueError("convention nodes must be flat under nodes/")
'''


def _detect(source: str, finder, location: str = _SAMPLE_LOCATION) -> List[Violation]:
    tree = ast.parse(source)
    return finder(tree, source.splitlines(), location)


@pytest.mark.parametrize(
    "finder, fault, clean",
    [
        (find_hardcoded_toolkit_roots, _FAULT_TOOLKIT_ROOT, _CLEAN_TOOLKIT_ROOT),
        (find_source_depth_walks, _FAULT_DEPTH_WALK, _CLEAN_DEPTH_WALK),
        (find_raising_resolvers, _FAULT_DEGRADES, _CLEAN_DEGRADES),
    ],
    ids=["toolkit-root", "depth-walk", "degrades"],
)
def test_detector_fires_on_fault_and_not_on_fix(finder, fault, clean):
    """Each detector is proven to fail on the fault and pass on the fix."""
    fired = _detect(fault, finder)
    assert fired, (
        f"{finder.__name__} did not fire on the injected fault — a rule that "
        f"cannot fail is a stub, not a gate."
    )
    for violation in fired:
        assert ":" in violation.location, "violation must name file:line"

    spurious = _detect(clean, finder)
    assert not spurious, (
        f"{finder.__name__} fired on COMPLIANT shapes, which would push the "
        f"next author back to the anti-pattern:\n"
        + "\n".join(f"  - {v.location}: {v.detail}" for v in spurious)
    )


def test_suppression_silences_a_real_violation():
    """The suppress-and-clean opt-out works and is per-rule."""
    line = '    nodes = find_repo_root() / "src" / "atdd"'
    suppressed = _FAULT_TOOLKIT_ROOT.replace(
        line.strip(),
        line.strip() + f"  # {_suppression_marker(_RULE_TOOLKIT_ROOT.rule_id)}",
    )
    assert _detect(_FAULT_TOOLKIT_ROOT, find_hardcoded_toolkit_roots)
    assert not _detect(suppressed, find_hardcoded_toolkit_roots), (
        "an inline suppression must silence the site it sits on"
    )


# ===========================================================================
# The gates — one per rule, each named by its node's implementation.ref.
# ===========================================================================
def _violations_for(rule_id: str) -> List[Violation]:
    core_root = core_source_root()
    if core_root is None:
        pytest.skip(
            "toolkit-self rule: core ships as an installed package here, so "
            "there is no core source tree in this repo to audit."
        )
    return [v for v in scan_core_source(core_root) if v.rule_id == rule_id]


def _fail(rule_id: str, violations: List[Violation]) -> None:
    formatted = "\n".join(f"  - {v.location}: {v.detail}" for v in violations)
    pytest.fail(
        f"\n{len(violations)} unsuppressed {rule_id} violation(s) in core:\n\n"
        f"{formatted}\n\n"
        "atdd dogfoods itself — a toolkit-layout hardcode breaks the toolkit "
        "for every consumer, where core ships as an installed package. Fix the "
        "site, or suppress it inline with a reason if it is genuinely the "
        "sanctioned shape. The destination for this rule is zero."
    )


def test_no_hardcoded_toolkit_root():
    """Core never joins 'src/atdd' onto a repo root without degrading."""
    violations = _violations_for(_RULE_TOOLKIT_ROOT.rule_id)
    if violations:
        _fail(_RULE_TOOLKIT_ROOT.rule_id, violations)


def test_no_source_depth_walk():
    """Core never derives a root by counting directories up from __file__."""
    violations = _violations_for(_RULE_DEPTH_WALK.rule_id)
    if violations:
        _fail(_RULE_DEPTH_WALK.rule_id, violations)


def test_resolver_degrades_not_raises():
    """Root resolvers return None on absence instead of raising."""
    violations = _violations_for(_RULE_DEGRADES.rule_id)
    if violations:
        _fail(_RULE_DEGRADES.rule_id, violations)
