"""
Prevent hand-rolled ``GitHubClient`` stubs from hiding method-name drift.

Scans ``src/atdd/coach/commands/tests/**/*.py`` for classes whose name
contains ``GitHubClient``. Any such class must either:

1. Explicitly subclass the real ``GitHubClient`` (so signatures come from the
   real class), OR
2. Not exist — tests should use
   ``unittest.mock.create_autospec(GitHubClient, instance=True)`` instead.

Hand-rolled plain classes are rejected because they silently accept any
method name the caller happens to invoke, letting production call sites
drift away from the real client surface without any test catching it. The
originating bug (issue #304) had the since-removed ``IssueManager.sync_wmbts`` calling
``client.list_sub_issues(...)``, a method that does not exist on the real
``GitHubClient``; every test passed because the fakes also defined
``list_sub_issues``.

Convention:
    src/atdd/tester/conventions/red.convention.yaml → ``mock_discipline``

Related: #304 — fix(atdd): Github Client Mock Drift.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List, NamedTuple, Set

import pytest

from atdd.coach.utils.repo import find_repo_root

# Toolkit dogfood: asserts on toolkit-only repo content (#1475).
pytestmark = [pytest.mark.platform]

REPO_ROOT = find_repo_root()
TESTS_ROOT = REPO_ROOT / "src" / "atdd" / "coach" / "commands" / "tests"
CLIENT_NAME = "GitHubClient"


class _Offense(NamedTuple):
    path: Path
    lineno: int
    class_name: str
    reason: str


def _iter_test_files(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if p.name != "__init__.py")


def _base_names(bases: List[ast.expr]) -> List[str]:
    names: List[str] = []
    for base in bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return names


def _find_hand_rolled_stubs(path: Path) -> List[_Offense]:
    """Return one Offense per class in ``path`` that names ``GitHubClient``
    in its identifier but does not subclass the real ``GitHubClient``.

    Leading underscore classes (e.g. ``_FakeGithubClient``) are still
    checked — the whole point is that any class declaration modelling the
    GitHub client must carry the real signatures.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    offenses: List[_Offense] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        normalized = node.name.lower()
        if "githubclient" not in normalized:
            continue
        bases = _base_names(node.bases)
        if CLIENT_NAME in bases:
            continue
        offenses.append(
            _Offense(
                path=path,
                lineno=node.lineno,
                class_name=node.name,
                reason=(
                    "hand-rolled GitHubClient stub — use "
                    "create_autospec(GitHubClient, instance=True) or "
                    f"subclass {CLIENT_NAME}"
                ),
            )
        )
    return offenses


def _scan(root: Path, *, exclude: Set[Path] = frozenset()) -> List[_Offense]:
    offenses: List[_Offense] = []
    for path in _iter_test_files(root):
        if path in exclude:
            continue
        offenses.extend(_find_hand_rolled_stubs(path))
    return offenses


def _format_offenses(offenses: List[_Offense]) -> str:
    lines = [
        f"  {off.path.relative_to(REPO_ROOT)}:{off.lineno}: "
        f"class {off.class_name} — {off.reason}"
        for off in offenses
    ]
    return "\n".join(lines)


@pytest.mark.coach
def test_no_hand_rolled_github_client_stubs():
    """Fail if any test file under ``src/atdd/coach/commands/tests/`` declares
    a class whose name contains ``GitHubClient`` without explicitly
    subclassing the real ``GitHubClient``.

    Given: the tests tree under ``src/atdd/coach/commands/tests/``
    When:  walking each ``.py`` file and parsing every ``class`` declaration
    Then:  any class naming the GitHub client must inherit from the real
           class; otherwise tests should use ``create_autospec`` instead
    """
    if not TESTS_ROOT.exists():
        pytest.skip(f"Tests root not found: {TESTS_ROOT}")

    offenses = _scan(TESTS_ROOT)
    if offenses:
        pytest.fail(
            f"\n\n{len(offenses)} hand-rolled GitHubClient stub(s) found — "
            "these hide method-name drift (see #304):\n\n"
            + _format_offenses(offenses)
            + "\n\nFix: replace with "
            "`create_autospec(GitHubClient, instance=True)` or subclass "
            "`GitHubClient` explicitly.\n"
            "Convention: src/atdd/tester/conventions/red.convention.yaml "
            "(mock_discipline)\n"
        )
