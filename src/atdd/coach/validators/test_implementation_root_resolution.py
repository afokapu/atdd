# URN: component:govern-lifecycle:enforcement-substrate:test_implementation_root_resolution:backend:domain
# Runtime: python
# Purpose: Enforce coach.graph.implementation-root-resolution — core must not anchor stack paths at the repo root (issue #1476).

"""Config-driven implementation-root enforcement (issue #1476, closes #689).

``coach.graph.implementation-root-resolution`` says implementation roots are
declared in ``.atdd/config.yaml`` and handed to resolvers as arguments — never
frozen into validator source. Until #1476 the rule was ``documentation-only``:
it stated the invariant and gated nothing, so 57 core modules drifted back to
``REPO_ROOT / "python"`` and a consumer whose backend is laid out as
``python/<wagon>/`` (no ``app.py``) failed four train-infrastructure tests it
had no way to satisfy (#689).

This validator is what makes the rule real. It walks the toolkit's own source
and fails on any repo-root-anchored *stack* path — the hardcode the convention
forbids. The fix is always the same: call
``atdd.coach.utils.config.resolve_code_root`` (source scans) or
``resolve_stack_container`` (manifests, sibling trees), and skip the stack when
the resolver returns ``None``.

Scope: toolkit-self. The rule governs *core's* source, so the scan is rooted at
``src/atdd`` and no-ops in a consumer repo, where core ships as an installed
package the consumer cannot edit.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Optional, Set

import pytest

from atdd.coach.utils.config import (
    DEFAULT_CODE_ROOTS,
    DEFAULT_STACK_CONTAINERS,
)
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation


pytestmark = [pytest.mark.coach]


_RULE = bind_rule("coach.graph.implementation-root-resolution")


# The stack vocabulary core knows about. The two default maps are the
# declaration surface; `typescript`/`frontend` are legacy aliases that older
# validators scanned for and that consumers may still declare under `code:`.
STACK_NAMES: Set[str] = (
    set(DEFAULT_CODE_ROOTS) | set(DEFAULT_STACK_CONTAINERS) | {"typescript", "frontend"}
)

# Names that denote the repository root. A stack path anchored at any of these
# is a hardcode; a path anchored at a *resolved* root (python_root, web_dir, …)
# is exactly what the convention asks for and is not flagged.
_REPO_ROOT_NAMES = {"REPO_ROOT", "ROOT", "repo_root", "root", "PROJECT_ROOT", "project_root"}
_REPO_ROOT_CALLS = {"find_repo_root", "get_repo_root"}


# Structural exemptions. Neither is a suppression: both are places where the
# pattern is not a resolver hardcoding a root.
#
#   config.py  — the declaration surface itself. DEFAULT_CODE_ROOTS has to name
#                `python` somewhere or there is no default to resolve. This is
#                the single module the convention exists to concentrate.
#   fixtures/  — inert sample sources fed to other validators as test data.
#                They are strings-on-disk, not resolvers; several deliberately
#                contain the violating shape so a detector can be proven to
#                catch it.
_EXEMPT_FILES = {Path("coach") / "utils" / "config.py"}
_EXEMPT_DIR_NAMES = {"fixtures"}


def _is_repo_root(node: ast.expr) -> bool:
    """True when *node* evaluates to the repository root."""
    if isinstance(node, ast.Name):
        return node.id in _REPO_ROOT_NAMES
    if isinstance(node, ast.Call):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        return name in _REPO_ROOT_CALLS
    return False


def _joined_path(node: ast.BinOp) -> Optional[str]:
    """Return ``"web/src"`` for ``REPO_ROOT / "web" / "src"``, else ``None``.

    Only the outermost chain matters: reporting the inner ``REPO_ROOT / "web"``
    of ``REPO_ROOT / "web" / "src"`` separately would double-count one site and
    hide which stack path was actually meant.
    """
    segments: List[str] = []
    current: ast.expr = node
    while (
        isinstance(current, ast.BinOp)
        and isinstance(current.op, ast.Div)
        and isinstance(current.right, ast.Constant)
        and isinstance(current.right.value, str)
    ):
        segments.append(current.right.value)
        current = current.left
    if not segments or not _is_repo_root(current):
        return None
    segments.reverse()
    return "/".join(segments)


def find_hardcoded_stack_roots(source: str, location: str) -> List[Violation]:
    """Return a violation for every repo-root-anchored stack path in *source*."""
    try:
        tree = ast.parse(source, filename=location)
    except SyntaxError:
        # Unparseable core source is somebody else's failure to report.
        return []

    # A BinOp that is the left operand of another `/` BinOp is an inner link of
    # a longer chain; only the outermost link is a distinct site.
    inner: Set[int] = {
        id(n.left)
        for n in ast.walk(tree)
        if isinstance(n, ast.BinOp)
        and isinstance(n.op, ast.Div)
        and isinstance(n.left, ast.BinOp)
    }

    violations: List[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or id(node) in inner:
            continue
        joined = _joined_path(node)
        if joined is None:
            continue
        stack = joined.split("/")[0]
        if stack not in STACK_NAMES:
            continue
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=f"{location}:{node.lineno}",
                detail=(
                    f"implementation root {joined!r} is hardcoded against the "
                    f"repo root. Resolve it from config instead: "
                    f"resolve_code_root({stack!r}, REPO_ROOT) for source scans, "
                    f"resolve_stack_container({stack!r}, REPO_ROOT) for manifests "
                    f"and sibling trees — and skip the stack when it returns None."
                ),
            )
        )
    return violations


def scan_core_source(core_root: Path) -> List[Violation]:
    """Walk *core_root* and collect every hardcoded-stack-root violation."""
    violations: List[Violation] = []
    for path in sorted(core_root.rglob("*.py")):
        relative = path.relative_to(core_root)
        if relative in _EXEMPT_FILES:
            continue
        if _EXEMPT_DIR_NAMES.intersection(relative.parts):
            continue
        violations.extend(
            find_hardcoded_stack_roots(
                path.read_text(encoding="utf-8"), str(relative)
            )
        )
    return violations


def _core_source_root() -> Optional[Path]:
    """The toolkit's own source tree, or None when core is an installed package."""
    candidate = find_repo_root() / "src" / "atdd"
    return candidate if candidate.is_dir() else None


@pytest.mark.coach
def test_no_hardcoded_stack_roots():
    """Core resolves implementation roots from config, never from source."""
    core_root = _core_source_root()
    if core_root is None:
        pytest.skip(
            "toolkit-self rule: core ships as an installed package here, so "
            "there is no core source tree in this repo to audit."
        )

    violations = scan_core_source(core_root)
    if not violations:
        return

    formatted = "\n".join(f"  - {v.location}: {v.detail}" for v in violations)
    pytest.fail(
        f"\n{len(violations)} hardcoded implementation root(s) in core "
        f"(coach.graph.implementation-root-resolution):\n\n{formatted}\n\n"
        "Roots are declared in .atdd/config.yaml::code (and ::stack_containers) "
        "and handed to resolvers as arguments. Hardcoding them here freezes a "
        "stack-specific layout into core and breaks consumers that lay their "
        "code out differently (see #689)."
    )


__all__ = [
    "find_hardcoded_stack_roots",
    "scan_core_source",
    "test_no_hardcoded_stack_roots",
]
