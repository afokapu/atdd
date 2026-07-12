"""Shared helpers for the canonical theme-taxonomy validators (issue #970).

This module is the single source of truth for the canonical theme set, the
commons-vs-coach boundary, and the mandatory digit-0 (commons) floor. The five
theme validators (``test_theme_must_be_canonical``,
``test_theme_commons_coach_boundary``, ``test_theme_urn_namespace_matches``,
``test_theme_archetype_alignment``, ``test_theme_zero_mandatory``) import from
here so the taxonomy lives in exactly one place.

Convention: src/atdd/planner/conventions/theme.convention.yaml

The digit-0 token is LOCKED to "commons" (operator decision #970).
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, List, Mapping, Optional, Tuple

import yaml

from atdd.coach.utils.config import load_atdd_config
from atdd.coach.utils.theme_map import get_theme_map

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Digit-0 theme name. LOCKED to "commons" by operator decision (#970) — NOT
# platform. Single source for the digit-0 name (mirrored in
# theme.convention.yaml::taxonomy.theme_zero_token). Beyond naming, digit 0 is
# the MANDATORY non-removable floor of every resolved theme set (see
# resolve_theme_set / planner.theme.theme-zero-mandatory).
# ---------------------------------------------------------------------------
CANONICAL_THEME_0: str = "commons"

#: The toolkit's OWN abstraction-stack themes (digits 0-4), documentary only.
#: As of #1317 this tuple is NOT the enforcement source — the canonical set is
#: resolved per-repo from ``get_theme_map(config)`` (see ``canonical_theme_set``)
#: so a consumer/game repo governs against its own effective map. It remains as
#: the value the toolkit's own ``.atdd/config.yaml`` ``themes:`` block declares.
CANONICAL_THEMES: Tuple[str, ...] = (
    CANONICAL_THEME_0,
    "plan",
    "test",
    "code",
    "coach",
)

#: digit -> canonical theme name for the toolkit's own abstraction stack (0-4).
#: Used by ``resolve_theme_set`` / theme-zero-mandatory as the pinned floor;
#: the must-be-canonical membership check instead defers to ``get_theme_map``.
CANONICAL_DIGIT_MAP: Dict[str, str] = {
    "0": CANONICAL_THEME_0,
    "1": "plan",
    "2": "test",
    "3": "code",
    "4": "coach",
}

#: Themes whose wagons map onto a non-coach archetype source root.
ARCHETYPE_THEME_ROOTS: Dict[str, str] = {
    "plan": "src/atdd/planner",
    "test": "src/atdd/tester",
    "code": "src/atdd/coder",
}

# NOTE (#1317): the former static ``RETIRED_THEMES`` reject list was removed.
# A theme is "retired"/non-canonical iff it is ABSENT from the effective
# ``get_theme_map(config)`` — so the validator and get_theme_map can never
# disagree on the same theme (a name can no longer be both blessed by the map
# and rejected as retired). Retirement is now purely the complement of the
# effective map, resolved per-repo.

#: Wagons whose theme correction + URN re-namespacing is deferred to the #951
#: recompose co-land. The repo-wide boundary/URN checks exclude these so the
#: enforcement slice lands green while the data migration is tracked, not yet
#: applied. SINGLE SOURCE — delete entries here as #951 re-themes each wagon.
DEFERRED_RETHEME_WAGONS: frozenset = frozenset(
    {
        "mediate-worker-decisions",
        # consolidate-coach-workspace is coach functionality currently themed
        # commons; its enforce-surface-conformance feature legitimately reuses the
        # #470 coach naming primitive + the coach multiplexer (live smoke). The
        # theme correction to `coach` co-lands with the #951 recompose (#865).
        "consolidate-coach-workspace",
    }
)


@dataclass(frozen=True)
class ThemeViolation:
    """A single theme-taxonomy violation surfaced by a validator."""

    rule_id: str
    wagon: str
    theme: str
    detail: str
    path: str


def canonical_theme_set(config: Optional[Mapping]) -> FrozenSet[str]:
    """Return the effective canonical theme set for *config* (#1317).

    Single source of truth = ``get_theme_map(config)``: the built-in defaults
    merged with the ``.atdd/config.yaml`` ``themes:`` overrides. The canonical
    set is exactly the set of names that map resolves to, so a consumer/game
    repo governs against its own effective taxonomy and the validator can never
    disagree with ``get_theme_map`` on any theme.
    """
    return frozenset(get_theme_map(config).values())


def is_canonical_theme(theme: str, config: Optional[Mapping] = None) -> bool:
    """Return True iff *theme* is in the effective canonical set for *config*.

    With no config the built-in defaults are used (``get_theme_map(None)``).
    """
    return theme in canonical_theme_set(config)


def drop_deferred(violations: List["ThemeViolation"]) -> List["ThemeViolation"]:
    """Filter out violations for wagons deferred to the #951 re-theme co-land."""
    return [v for v in violations if v.wagon not in DEFERRED_RETHEME_WAGONS]


# ---------------------------------------------------------------------------
# Implementations (GREEN, #970).
# ---------------------------------------------------------------------------
#: theme -> archetype source-root segment under src/atdd/.
_ARCHETYPE_FOR_THEME: Dict[str, str] = {"plan": "planner", "test": "tester", "code": "coder"}


def _iter_wagon_manifests(repo_root: Path):
    """Yield (manifest_data, manifest_path) for every plan/<wagon>/_<wagon>.yaml.

    Only the wagon manifest (``_<dir>.yaml``) is matched — feature specs, WMBT
    files, and the top-level plan/_wagons.yaml / _trains.yaml are skipped.
    """
    plan_dir = repo_root / "plan"
    if not plan_dir.is_dir():
        return
    for mf in sorted(plan_dir.glob("*/_*.yaml")):
        if mf.name != f"_{mf.parent.name}.yaml":
            continue
        try:
            data = yaml.safe_load(mf.read_text()) or {}
        except (OSError, yaml.YAMLError) as exc:
            _log.warning(
                "theme taxonomy: skipping unreadable wagon manifest",
                extra={"path": str(mf), "error": repr(exc)},
            )
            continue
        if isinstance(data, dict) and "wagon" in data and "theme" in data:
            yield data, mf


def _wagon_src_dir(repo_root: Path, wagon_slug: str) -> Path:
    """Convention mapping: wagon slug -> src/atdd/<slug_with_underscores>/."""
    return repo_root / "src" / "atdd" / wagon_slug.replace("-", "_")


def _module_imports_coach(py_path: Path) -> bool:
    """True iff *py_path* imports the atdd.coach package (AST-accurate)."""
    try:
        tree = ast.parse(py_path.read_text())
    except (OSError, SyntaxError, ValueError) as exc:
        _log.warning(
            "theme taxonomy: skipping unparseable module in commons-coach scan",
            extra={"path": str(py_path), "error": repr(exc)},
        )
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "atdd.coach" or a.name.startswith("atdd.coach.") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "atdd.coach" or mod.startswith("atdd.coach."):
                return True
            if mod == "atdd" and any(a.name == "coach" for a in node.names):
                return True
    return False


def scan_wagon_themes(repo_root: Path) -> Dict[str, Tuple[str, str]]:
    """Map wagon-slug -> (theme, manifest_path) for every plan/<wagon>/_<wagon>.yaml."""
    out: Dict[str, Tuple[str, str]] = {}
    for data, mf in _iter_wagon_manifests(repo_root):
        out[data["wagon"]] = (data["theme"], str(mf))
    return out


def check_must_be_canonical(repo_root: Path) -> List[ThemeViolation]:
    """Flag every wagon whose ``theme:`` is absent from the effective map.

    #1317: the canonical set is resolved from ``get_theme_map`` applied to the
    repo's own ``.atdd/config.yaml`` (``canonical_theme_set``), so a game/
    consumer repo governs against its declared game-domain themes while the
    toolkit's own repo (whose config declares ``plan/test/code/coach``)
    continues to reject those game names.
    """
    config = load_atdd_config(repo_root)
    allowed = canonical_theme_set(config)
    viols: List[ThemeViolation] = []
    for data, mf in _iter_wagon_manifests(repo_root):
        theme = data["theme"]
        if theme not in allowed:
            viols.append(
                ThemeViolation(
                    rule_id="planner.theme.must-be-canonical",
                    wagon=data["wagon"],
                    theme=theme,
                    detail=(
                        f"theme {theme!r} is not in the effective theme map "
                        f"{sorted(allowed)} (get_theme_map + .atdd/config.yaml themes)"
                    ),
                    path=str(mf),
                )
            )
    return viols


def check_commons_coach_boundary(repo_root: Path) -> List[ThemeViolation]:
    """Flag every ``commons``-themed wagon whose src imports ``atdd.coach``."""
    viols: List[ThemeViolation] = []
    for data, _mf in _iter_wagon_manifests(repo_root):
        if data["theme"] != CANONICAL_THEME_0:
            continue
        src = _wagon_src_dir(repo_root, data["wagon"])
        if not src.is_dir():
            continue
        for py in sorted(src.rglob("*.py")):
            if _module_imports_coach(py):
                viols.append(
                    ThemeViolation(
                        rule_id="planner.theme.commons-coach-boundary",
                        wagon=data["wagon"],
                        theme=data["theme"],
                        detail=f"commons wagon imports atdd.coach in {py.name}",
                        path=str(py),
                    )
                )
                break
    return viols


def check_urn_namespace_matches(repo_root: Path) -> List[ThemeViolation]:
    """Flag produced contract/telemetry URNs whose theme-prefix != wagon theme."""
    viols: List[ThemeViolation] = []
    for data, mf in _iter_wagon_manifests(repo_root):
        theme = data["theme"]
        for produced in data.get("produce") or []:
            if not isinstance(produced, dict):
                continue
            name = produced.get("name") or ""
            if ":" not in name:
                continue
            prefix = name.split(":", 1)[0]
            if prefix != theme:
                viols.append(
                    ThemeViolation(
                        rule_id="planner.theme.urn-namespace-matches",
                        wagon=data["wagon"],
                        theme=theme,
                        detail=f"produced URN {name!r} theme-prefix {prefix!r} != wagon theme {theme!r}",
                        path=str(mf),
                    )
                )
    return viols


def check_archetype_alignment(repo_root: Path) -> List[ThemeViolation]:
    """Flag plan/test/code wagons whose impl lives outside the archetype root."""
    viols: List[ThemeViolation] = []
    src_root = repo_root / "src" / "atdd"
    for data, _mf in _iter_wagon_manifests(repo_root):
        theme = data["theme"]
        expected = _ARCHETYPE_FOR_THEME.get(theme)
        if expected is None:
            continue  # commons / coach have no archetype-root constraint
        if not src_root.is_dir():
            continue
        under = data["wagon"].replace("-", "_")
        found = [p for p in src_root.rglob(under) if p.is_dir()]
        if not found:
            continue  # documentation-only: source not locatable by slug
        for p in found:
            parts = p.relative_to(src_root).parts
            if expected not in parts:
                viols.append(
                    ThemeViolation(
                        rule_id="planner.theme.archetype-alignment",
                        wagon=data["wagon"],
                        theme=theme,
                        detail=f"source {p} is not under src/atdd/{expected}/ (theme {theme!r})",
                        path=str(p),
                    )
                )
    return viols


def resolve_theme_set(config: Optional[Mapping]) -> Dict[str, str]:
    """Resolve digit->theme name from *config*, pinning digit 0 to commons.

    Starts from the canonical digit map (0-4), applies any consumer ``themes:``
    overrides for digits 1-9, then ALWAYS pins digit 0 to CANONICAL_THEME_0
    (commons) — an override that tries to remove or rename digit 0 is ignored.
    The returned map therefore always contains commons at digit 0.
    """
    resolved: Dict[str, str] = dict(CANONICAL_DIGIT_MAP)
    overrides: Optional[Mapping] = None
    if isinstance(config, Mapping):
        candidate = config.get("themes")
        if isinstance(candidate, Mapping):
            overrides = candidate
    if overrides:
        for raw_key, raw_value in overrides.items():
            key = str(raw_key)
            if key == "0":
                continue  # never let an override touch the mandatory floor
            if isinstance(raw_value, str) and raw_value:
                resolved[key] = raw_value
    resolved["0"] = CANONICAL_THEME_0  # pin the non-removable commons floor
    return resolved


def check_theme_zero_mandatory(config: Optional[Mapping]) -> List[ThemeViolation]:
    """Confirm the resolved theme set always contains the commons floor.

    Returns a violation if a resolved theme map (defaults, or defaults merged
    with consumer overrides) omits or renames digit-0 commons.
    """
    resolved = resolve_theme_set(config)
    if resolved.get("0") != CANONICAL_THEME_0 or CANONICAL_THEME_0 not in resolved.values():
        return [
            ThemeViolation(
                rule_id="planner.theme.theme-zero-mandatory",
                wagon="<resolved-theme-set>",
                theme=resolved.get("0", ""),
                detail=f"digit-0 floor {CANONICAL_THEME_0!r} missing from resolved set {resolved!r}",
                path=".atdd/config.yaml",
            )
        ]
    return []
