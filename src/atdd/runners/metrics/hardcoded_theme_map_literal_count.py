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
   ``'0'..'9'`` AND whose values all name themes — backstop for inlined
   theme maps.

   The value check is what makes pattern 3 a theme-map detector rather
   than a digit-keyed-dict detector (#1927). Without it the backstop
   counted train-category maps (``{"0": "nominal", "1": "error", ...}``,
   three sites), an interactive prompt's choice map, and every test
   fixture that passes a ``themes:`` override — 22 of the 23 literals it
   reported across the toolkit were not theme maps at all. That
   false-positive rate went unobserved because the count was never read:
   D010's threshold reached ``passes()`` stringified, so every comparison
   raised and was swallowed (#1925).

   The narrowing is deliberate about what it gives up, and it gives up two
   things. An inlined map of entirely *custom* theme names is
   indistinguishable from any other digit-keyed dict. And because EVERY
   value must name a theme, a map mixing canonical and custom names
   (``{"0": "commons", "1": "qualification"}``) escapes too.

   Requiring every value rather than merely one is what keeps the backstop
   honest: several theme names are ordinary English words, so a single
   incidental hit would re-introduce false positives on maps like
   ``{"1": "test", "2": "prod"}``. Both gaps are covered by patterns 1 and 2
   whenever the literal is bound to ``theme_map`` or ``valid_themes``, which
   is the case D010's acceptance text actually describes.

Exempt files (neither is a second source of truth):

* ``**/theme_map.py`` — the helper itself declares the canonical mapping.
* test modules (``test_*.py``, ``*_test.py``, or anything under a
  ``tests/`` directory) — a test that pins ``DEFAULT_THEME_MAP``'s value
  has to state that value; the literal IS the assertion (#1927).

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


def _theme_vocabulary() -> frozenset:
    """Every name the toolkit recognises as a theme.

    Sourced from ``coach.utils.theme_map`` so this metric cannot drift from
    the module it polices. Falls back to the shipped defaults if the import
    is unavailable (the metric must stay importable in a consumer repo that
    vendored only the runner).
    """
    names = set()
    try:
        from atdd.coach.utils.theme_map import (
            CANONICAL_DIGIT_MAP,
            DEFAULT_THEME_MAP,
        )
        names.update(DEFAULT_THEME_MAP.values())
        names.update(CANONICAL_DIGIT_MAP.values())
    except ImportError:  # pragma: no cover - vendored-runner fallback
        names.update({
            "commons", "mechanic", "scenario", "match", "sensory",
            "player", "league", "audience", "monetization", "partnership",
            "plan", "test", "code", "coach",
        })
    return frozenset(names)


def _is_test_module(path: Path) -> bool:
    """True for a test module, by filename or by living under ``tests/``."""
    name = path.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return "tests" in path.parts


def _iter_python_files(scan_root: Path) -> Iterable[Path]:
    """Yield every ``.py`` file under *scan_root*, exempting theme_map.py."""
    for path in scan_root.rglob("*.py"):
        if path.name == "theme_map.py":
            continue
        if _is_test_module(path):
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


def _is_digit_keyed_dict(node: ast.Dict, vocabulary: frozenset) -> bool:
    """Dict mapping single-digit strings to theme names.

    BOTH halves are required. Digit keys alone describe a train-category map,
    a menu, a retry table — anything indexed by a small integer. What makes
    the literal a *theme map* is that its values name themes (#1927).
    """
    if not node.keys:
        return False
    for key in node.keys:
        if not isinstance(key, ast.Constant):
            return False
        if not isinstance(key.value, str) or key.value not in _DIGIT_KEYS:
            return False
    for value in node.values:
        if not isinstance(value, ast.Constant):
            return False
        if not isinstance(value.value, str):
            return False
        if value.value not in vocabulary:
            return False
    return True


def _count_in_tree(tree: ast.AST, vocabulary: frozenset | None = None) -> int:
    """Count all three patterns in *tree*; assignments and dicts are
    counted independently so a digit-keyed ``theme_map`` literal scores
    twice (once as the named assignment, once as the heuristic backstop).
    """
    vocab = _theme_vocabulary() if vocabulary is None else vocabulary
    total = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if _is_theme_map_assignment(node):
                total += 1
            elif _is_valid_themes_assignment(node):
                total += 1
        elif isinstance(node, ast.Dict) and _is_digit_keyed_dict(node, vocab):
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

    vocabulary = _theme_vocabulary()
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
        total += _count_in_tree(tree, vocabulary)
    return total


def passes(value: int, threshold: int) -> bool:
    """Upper-bound semantics: ``value <= threshold`` (0 is the goal)."""
    return value <= threshold


__all__ = ["compute", "passes"]
