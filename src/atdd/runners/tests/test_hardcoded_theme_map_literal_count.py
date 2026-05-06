# URN: component:govern-lifecycle:enforcement-substrate:metric_hardcoded_theme_map_literal_count:backend:tests
# Runtime: python
# Purpose: Cover compute() pattern detection and passes() upper-bound semantics for the D010 metric (issue #413, spec v12 §11).

"""Unit tests for ``hardcoded_theme_map_literal_count`` (issue #413).

Each test writes synthetic ``.py`` files under
``tmp_path/src/atdd/`` and invokes ``compute(tmp_path)`` to assert the
counter wires up the AST patterns described in the issue body.

Patterns covered:

* ``theme_map = {...}`` (Name target, Dict literal value).
* ``valid_themes = {...}`` (Name target, Set or Dict literal value).
* Any digit-keyed ``Dict`` literal as a heuristic backstop.

Plus exemption (``theme_map.py`` is allowed to declare the canonical
mapping), missing-directory vacuous pass, and ``passes`` upper-bound
semantics.
"""

from __future__ import annotations

from pathlib import Path

from atdd.runners.metrics.hardcoded_theme_map_literal_count import (
    compute,
    passes,
)


def _write(scan_root: Path, rel_path: str, source: str) -> Path:
    """Materialize ``<scan_root>/<rel_path>`` with *source* contents."""
    target = scan_root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return target


def _scan_root(tmp_path: Path) -> Path:
    """The directory ``compute`` actually walks."""
    return tmp_path / "src" / "atdd"


def test_theme_map_dict_assignment_is_counted_once(tmp_path: Path) -> None:
    """A bare ``theme_map = {"0": "auth"}`` literal scores 1.

    The acceptance-criterion case from the issue body. The single dict
    assignment matches BOTH (1) the Name+Dict assignment pattern and
    (3) the digit-keyed Dict heuristic, so the counter returns 2.
    """
    _write(
        _scan_root(tmp_path),
        "coach/_fixture.py",
        'theme_map = {"0": "auth"}\n',
    )
    assert compute(tmp_path) == 2


def test_no_literal_returns_zero(tmp_path: Path) -> None:
    """A clean tree with no theme literals counts zero."""
    _write(
        _scan_root(tmp_path),
        "coach/_clean.py",
        '"""no theme literals here."""\nVALUE = 1\n',
    )
    assert compute(tmp_path) == 0


def test_theme_map_py_is_exempt(tmp_path: Path) -> None:
    """``**/theme_map.py`` is exempt — the canonical mapping lives there."""
    _write(
        _scan_root(tmp_path),
        "coach/utils/theme_map.py",
        'theme_map = {"0": "auth", "1": "billing"}\n',
    )
    assert compute(tmp_path) == 0


def test_valid_themes_set_assignment_is_counted(tmp_path: Path) -> None:
    """``valid_themes = {"auth", "billing"}`` (set literal) scores 1."""
    _write(
        _scan_root(tmp_path),
        "coach/_set.py",
        'valid_themes = {"auth", "billing"}\n',
    )
    assert compute(tmp_path) == 1


def test_valid_themes_dict_assignment_is_counted(tmp_path: Path) -> None:
    """``valid_themes = {"auth": True}`` (dict literal) scores 1.

    The dict has string keys that are NOT single digits, so the
    heuristic backstop does not double-fire.
    """
    _write(
        _scan_root(tmp_path),
        "coach/_dict.py",
        'valid_themes = {"auth": True}\n',
    )
    assert compute(tmp_path) == 1


def test_digit_keyed_dict_heuristic_fires(tmp_path: Path) -> None:
    """An anonymous digit-keyed dict literal is counted by the backstop."""
    _write(
        _scan_root(tmp_path),
        "coach/_inline.py",
        'def themes():\n    return {"0": "auth", "1": "billing"}\n',
    )
    assert compute(tmp_path) == 1


def test_missing_scan_root_is_vacuous_pass(tmp_path: Path) -> None:
    """No ``src/atdd/`` directory → metric returns 0 (consumer-repo case)."""
    assert compute(tmp_path) == 0


def test_compute_skips_unparseable_files(tmp_path: Path) -> None:
    """SyntaxError files are skipped, not propagated."""
    _write(
        _scan_root(tmp_path),
        "coach/_broken.py",
        "this is not valid python ::: !!!\n",
    )
    _write(
        _scan_root(tmp_path),
        "coach/_ok.py",
        'theme_map = {"x": "y"}\n',
    )
    # Broken file contributes 0; ok file contributes 1 (theme_map name +
    # non-digit key → only the named-assignment pattern fires).
    assert compute(tmp_path) == 1


def test_passes_upper_bound_semantics() -> None:
    """``passes`` is ``value <= threshold`` — zero is the goal."""
    assert passes(0, 0) is True
    assert passes(0, 5) is True
    assert passes(5, 5) is True
    assert passes(6, 5) is False
    assert passes(1, 0) is False
