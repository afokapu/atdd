# URN: component:govern-lifecycle:enforcement-substrate:metric_hardcoded_theme_map_literal_count:backend:domain
# Runtime: python
# Purpose: Toolkit-shipped metric for D010 — count hardcoded theme_map literals outside coach/utils/theme_map.py (spec v12 §4.5, §11).

"""Metric: ``hardcoded_theme_map_literal_count`` (issue #413).

Implements the canonical "first metric" (spec v12 §11) wired to D010's
``signal.metric``. Counts hardcoded theme_map literals that should have
been replaced by ``coach.utils.theme_map.get_theme_map(config)``.

Patterns counted (per issue body):

1. Assignment ``theme_map = {...}`` (Name target, Dict value).
2. Assignment ``valid_themes = {...}`` whose value is a set or dict
   literal of theme strings.
3. Any ``Dict`` literal whose keys are single-digit string literals
   ``'0'..'9'`` — heuristic backstop for inlined theme maps.

Files matching ``**/theme_map.py`` are exempt (the helper itself
declares the canonical mapping).

Toolkit-self-applicable: scans ``<repo_root>/src/atdd/``, which only
exists when the substrate runs against the toolkit's own checkout. In
consumer repos the directory is absent and ``compute`` returns ``0``
(vacuous pass).

Companion ``passes(value, threshold)`` enforces upper-bound semantics:
zero hardcoded literals is the goal.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable


_DIGIT_KEYS = frozenset("0123456789")


def _iter_python_files(scan_root: Path) -> Iterable[Path]:
    """Yield every ``.py`` file under *scan_root*, exempting theme_map.py."""
    for path in scan_root.rglob("*.py"):
        if path.name == "theme_map.py":
            continue
        yield path


def _is_theme_map_assignment(node: ast.Assign) -> bool:
    """``theme_map = {...}`` — a Name target and a Dict literal value."""
    if not isinstance(node.value, ast.Dict):
        return False
    return any(
        isinstance(t, ast.Name) and t.id == "theme_map" for t in node.targets
    )


def _is_valid_themes_assignment(node: ast.Assign) -> bool:
    """``valid_themes = {...}`` whose value is a set or dict literal."""
    if not isinstance(node.value, (ast.Set, ast.Dict)):
        return False
    return any(
        isinstance(t, ast.Name) and t.id == "valid_themes" for t in node.targets
    )


def _is_digit_keyed_dict(node: ast.Dict) -> bool:
    """Dict whose every key is a single-digit string literal ('0'..'9')."""
    if not node.keys:
        return False
    for key in node.keys:
        if not isinstance(key, ast.Constant):
            return False
        if not isinstance(key.value, str) or key.value not in _DIGIT_KEYS:
            return False
    return True


def _count_in_tree(tree: ast.AST) -> int:
    """Count all three patterns in *tree*; assignments and dicts are
    counted independently so a digit-keyed ``theme_map`` literal scores
    twice (once as the named assignment, once as the heuristic backstop).
    """
    total = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if _is_theme_map_assignment(node):
                total += 1
            elif _is_valid_themes_assignment(node):
                total += 1
        elif isinstance(node, ast.Dict) and _is_digit_keyed_dict(node):
            total += 1
    return total


def compute(repo_root: Path) -> int:
    """Return the number of hardcoded theme_map literals under
    ``<repo_root>/src/atdd/``, excluding ``**/theme_map.py``.

    Returns ``0`` when the directory does not exist (consumer repos
    vacuously pass — the metric is toolkit-self-applicable).
    """
    scan_root = Path(repo_root) / "src" / "atdd"
    if not scan_root.is_dir():
        return 0

    total = 0
    for py_file in _iter_python_files(scan_root):
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        total += _count_in_tree(tree)
    return total


def passes(value: int, threshold: int) -> bool:
    """Upper-bound semantics: ``value <= threshold`` (0 is the goal)."""
    return value <= threshold


__all__ = ["compute", "passes"]
