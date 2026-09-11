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

    The acceptance-criterion case from the issue body. It used to score 2 —
    the name-based pattern and the digit-keyed backstop both fired on the one
    literal, so the test's own name contradicted its assertion. Since #1927 the
    backstop also requires theme-named values, and ``"auth"`` is not one, so
    only the name-based pattern fires and the count is what the name says.
    """
    _write(
        _scan_root(tmp_path),
        "coach/_fixture.py",
        'theme_map = {"0": "auth"}\n',
    )
    assert compute(tmp_path) == 1


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
    """An anonymous digit→THEME dict literal is counted by the backstop.

    The fixture names real themes. Before #1927 any digit-keyed dict fired
    here regardless of its values, which is what made the backstop count
    train categories and menu maps; the values are now what qualify it.
    """
    _write(
        _scan_root(tmp_path),
        "coach/_inline.py",
        'def themes():\n    return {"0": "commons", "1": "plan"}\n',
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


# --- #1927: the backstop must measure theme-ness, not digit-keyed-ness -------
#
# Pattern 3 counted ANY dict whose keys are all single-digit strings. Across
# the toolkit that caught train-category maps, an interactive menu, and test
# fixtures — 22 of 23 hits were not theme maps at all. The count was never read
# (the threshold reached passes() stringified, #1925), so the false-positive
# rate was never observed. These pin what the backstop is actually for.


def test_train_category_digit_map_is_not_a_theme_map(tmp_path: Path) -> None:
    """``{"0": "nominal", "1": "error", ...}`` is a train category map.

    Three sites carry this exact literal (registry, viz_app, the URN
    migration). Its keys are digits and its values are categories; nothing
    about it duplicates the digit→theme mapping.
    """
    _write(
        _scan_root(tmp_path),
        "coach/commands/_registry.py",
        'CATEGORY_MAP = {"0": "nominal", "1": "error", '
        '"2": "alternate", "3": "exception"}\n',
    )
    assert compute(tmp_path) == 0


def test_interactive_menu_digit_map_is_not_a_theme_map(tmp_path: Path) -> None:
    """A prompt's choice map is digit-keyed and entirely unrelated."""
    _write(
        _scan_root(tmp_path),
        "coach/commands/_consumers.py",
        "direction_map = {'1': 'manifests', '2': 'contracts', '3': 'mutual'}\n",
    )
    assert compute(tmp_path) == 0


def test_a_theme_valued_digit_map_is_still_counted(tmp_path: Path) -> None:
    """The case the backstop exists for: an inlined digit→theme mapping.

    Values drawn from the theme vocabulary are what make a digit-keyed dict a
    theme map. This is the shape that genuinely duplicates the helper.
    """
    _write(
        _scan_root(tmp_path),
        "planner/validators/_taxonomy.py",
        'CANONICAL = {"0": "commons", "1": "plan", "2": "test", '
        '"3": "code", "4": "coach"}\n',
    )
    assert compute(tmp_path) == 1


def test_default_theme_map_inlined_elsewhere_is_counted(tmp_path: Path) -> None:
    """A copy of the shipped default mapping, anywhere but theme_map.py."""
    _write(
        _scan_root(tmp_path),
        "coach/_copy.py",
        'M = {"0": "commons", "1": "mechanic", "2": "scenario", '
        '"3": "match", "4": "sensory"}\n',
    )
    assert compute(tmp_path) == 1


def test_test_modules_are_exempt(tmp_path: Path) -> None:
    """A test pinning the canonical map must state the canonical map.

    ``test_custom_themes.py`` asserts ``DEFAULT_THEME_MAP == {...}``; that
    literal IS the assertion, not a second source of truth. Exempting test
    modules follows the exemption ``theme_map.py`` already carries.
    """
    _write(
        _scan_root(tmp_path),
        "planner/validators/test_custom_themes.py",
        'expected = {"0": "commons", "1": "mechanic", "2": "scenario"}\n'
        'def test_default_map_is_pinned():\n'
        '    assert expected == expected\n',
    )
    assert compute(tmp_path) == 0


def test_named_theme_map_in_a_test_module_is_still_exempt(tmp_path: Path) -> None:
    """The exemption is by module, not by pattern — fixtures name things too."""
    _write(
        _scan_root(tmp_path),
        "coach/validators/tests/test_themes.py",
        'theme_map = {"0": "commons"}\n',
    )
    assert compute(tmp_path) == 0


def test_named_theme_map_outside_tests_is_unaffected(tmp_path: Path) -> None:
    """Patterns 1 and 2 are name-based and keep firing in production code.

    Scoping the backstop must not weaken the two precise patterns: a
    ``theme_map = {...}`` literal is a violation whatever its values are.
    """
    _write(
        _scan_root(tmp_path),
        "coach/_fixture.py",
        'theme_map = {"0": "auth", "1": "billing"}\n',
    )
    assert compute(tmp_path) == 1
