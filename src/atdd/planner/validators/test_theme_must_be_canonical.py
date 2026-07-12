# Acceptance: acc:govern-lifecycle:C002-UNIT-001-non-canonical-theme-is-flagged
# Acceptance: acc:govern-lifecycle:C002-SMOKE-001-plan-tree-has-no-non-canonical-theme
# Acceptance: acc:govern-lifecycle:E001-UNIT-001-schema-pattern-accepts-custom-themes
"""planner.theme.must-be-canonical validator (issue #970; #1317 config-aware).

Enforces that every wagon ``theme:`` resolves to a canonical theme. As of #1317
the canonical set is no longer a hardcoded five — it is the effective,
consumer-repo-aware theme map ``get_theme_map(load_atdd_config(repo_root))``
(built-in defaults + ``.atdd/config.yaml`` ``themes:`` overrides). This is the
single source of truth shared with ``inventory``/``registry``/``sync``, so the
validator and ``get_theme_map`` can never disagree on the same theme.

In the toolkit's OWN repo the config's ``themes:`` block yields
commons/plan/test/code/coach; in a game/consumer repo it yields the game-domain
themes. A theme is non-canonical iff it is absent from the effective map — there
is no separate static reject list to contradict ``get_theme_map`` (#1317).

Rule: planner.theme.must-be-canonical (severity 3)
Convention: src/atdd/planner/conventions/theme.convention.yaml::rules
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.config import load_atdd_config
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.utils.theme_map import get_theme_map

from ._theme_taxonomy import (
    canonical_theme_set,
    check_must_be_canonical,
    is_canonical_theme,
)

pytestmark = [pytest.mark.planner]

_RULE_ID = "planner.theme.must-be-canonical"
# NOTE: pass the literal id (not _RULE_ID) so the reverse rule-coherence
# scanner — which only recognizes ``bind_rule("<literal>")`` — binds this rule.
_RULE = bind_rule("planner.theme.must-be-canonical")

REPO_ROOT = find_repo_root()

# Effective-map fixtures (as written to a tmp repo's .atdd/config.yaml).
TOOLKIT_THEMES = {0: "commons", 1: "plan", 2: "test", 3: "code", 4: "coach"}
GAME_THEMES = {
    0: "commons", 1: "mechanic", 2: "scenario", 3: "match",
    4: "sensory", 5: "player", 6: "league",
}


def _write_wagon(root: Path, wagon: str, theme: str) -> None:
    slug = wagon.replace("-", "_")
    d = root / "plan" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / f"_{slug}.yaml").write_text(
        f'wagon: {wagon}\nurn: "wagon:{wagon}"\ntheme: {theme}\n'
    )


def _write_config(root: Path, themes: dict) -> None:
    atdd = root / ".atdd"
    atdd.mkdir(parents=True, exist_ok=True)
    lines = ["themes:"] + [f"  {k}: {v}" for k, v in themes.items()]
    (atdd / "config.yaml").write_text("\n".join(lines) + "\n")


def test_every_wagon_theme_is_canonical() -> None:
    """Repo-wide: no wagon declares a theme outside the effective map."""
    violations = check_must_be_canonical(REPO_ROOT)
    assert violations == [], (
        f"[{_RULE_ID}] non-canonical wagon themes:\n"
        + "\n".join(f"  - {v.wagon}: theme={v.theme!r} ({v.path})" for v in violations)
    )


def test_game_repo_config_accepts_game_themes(tmp_path: Path) -> None:
    """Consumer/game repo whose config declares game themes → PASSES for
    match/mechanic/scenario/league wagons (acceptance #1)."""
    _write_config(tmp_path, GAME_THEMES)
    for wagon, theme in (
        ("run-match", "match"),
        ("own-territory", "mechanic"),
        ("curate-content", "scenario"),
        ("run-league", "league"),
    ):
        _write_wagon(tmp_path, wagon, theme)
    assert check_must_be_canonical(tmp_path) == []


def test_toolkit_config_rejects_out_of_map_theme(tmp_path: Path) -> None:
    """Toolkit-config repo → STILL enforces plan/test/code/coach: a game theme
    that the config maps away (mechanic → digit 1 = plan) is rejected
    (acceptance #2)."""
    _write_config(tmp_path, TOOLKIT_THEMES)
    _write_wagon(tmp_path, "own-territory", "mechanic")
    violations = check_must_be_canonical(tmp_path)
    assert any(v.theme == "mechanic" for v in violations), (
        "expected 'mechanic' to be rejected under the toolkit themes block"
    )


def test_toolkit_config_accepts_toolkit_themes(tmp_path: Path) -> None:
    """Under the toolkit themes block, commons/plan/test/code/coach all pass."""
    _write_config(tmp_path, TOOLKIT_THEMES)
    for theme in ("commons", "plan", "test", "code", "coach"):
        _write_wagon(tmp_path, f"w-{theme}", theme)
    assert check_must_be_canonical(tmp_path) == []


@pytest.mark.parametrize(
    "config",
    [{"themes": GAME_THEMES}, {"themes": TOOLKIT_THEMES}, {}, None],
)
def test_validator_never_disagrees_with_get_theme_map(config) -> None:
    """acceptance #3: every theme blessed by get_theme_map is canonical, and a
    theme absent from the effective map is not."""
    effective = get_theme_map(config)
    for theme in effective.values():
        assert is_canonical_theme(theme, config), (
            f"{theme!r} in get_theme_map but not canonical under {config!r}"
        )
    assert set(canonical_theme_set(config)) == set(effective.values())
    assert not is_canonical_theme("no-such-theme-xyz", config)


def test_is_canonical_theme_is_config_aware() -> None:
    """Same name, opposite verdict under different effective maps."""
    game = {"themes": GAME_THEMES}
    toolkit = {"themes": TOOLKIT_THEMES}
    assert is_canonical_theme("mechanic", game)
    assert not is_canonical_theme("mechanic", toolkit)
    assert is_canonical_theme("plan", toolkit)
    assert not is_canonical_theme("plan", game)
