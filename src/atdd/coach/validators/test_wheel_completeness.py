# URN: component:govern-lifecycle:enforcement-substrate:test_wheel_completeness:backend:domain
# Runtime: python
# Purpose: Build-time guard — every src-tree validator fixture must ship in the installed wheel.

"""
Coach validator for wheel-completeness (issue #451).

Source-tree inverse scan, NOT code AST: walk every file under
``<repo_root>/src/atdd/**/validators/fixtures/**`` and assert each one
exists at the corresponding path under
``Path(atdd.__file__).resolve().parent``.

Why inverse scan instead of parsing validator code for fixture references:
the AST approach is prone to false negatives on f-string / dynamic-path
patterns (``for bucket in (...): path = base / bucket / "harness_output.json"``).
The inverse scan walks the source tree directly and is impossible to
confuse — there is no parsing involved.

The validator ships at ``disposition: advisory`` for the 3.7.x line; flip
to ``strict`` in 3.8.0 once the install-path coverage is empirically
clean across the active consumer-repo fleet.

Editable install:
    When ``Path(atdd.__file__).resolve()`` is the repo's own
    ``src/atdd/__init__.py``, the source tree IS the wheel root, so the
    check is trivially satisfied. The validator ``pytest.skip``s in that
    case — value emerges in CI on a wheel-built environment, not local
    dev.

Convention: ``src/atdd/coach/conventions/wheel-completeness.convention.yaml``
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple

import pytest

import atdd
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation


pytestmark = [pytest.mark.coach, pytest.mark.platform]


_RULE = bind_rule("coach.wheel-completeness.fixture-missing-from-wheel")

# ---------------------------------------------------------------------------
# Cache-cruft exclusion (mirrors MANIFEST.in recursive-exclude directives)
# ---------------------------------------------------------------------------
_CACHE_CRUFT_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache"})
_CACHE_CRUFT_FILE_SUFFIXES = (".pyc", ".pyo")
_CACHE_CRUFT_FILE_NAMES = frozenset({".DS_Store"})


def _is_cache_cruft(path: Path) -> bool:
    """True iff *path* is a build-artifact / OS-cruft file we must not assert on.

    The MANIFEST.in directives strip these from the wheel; the inverse
    scan must equally skip them on the source side or we'd assert on
    files that legitimately don't ship.
    """
    if path.name in _CACHE_CRUFT_FILE_NAMES:
        return True
    if path.suffix in _CACHE_CRUFT_FILE_SUFFIXES:
        return True
    for part in path.parts:
        if part in _CACHE_CRUFT_DIR_NAMES:
            return True
    return False


# ---------------------------------------------------------------------------
# Repo-root + source-tree discovery
# ---------------------------------------------------------------------------
def find_repo_src_atdd() -> Path | None:
    """Return the source-tree ``src/atdd`` path for the repo this validator
    runs in, or ``None`` when no source tree is reachable.

    Walk parents of this file looking for the conventional layout marker
    (a sibling ``pyproject.toml`` next to ``src/atdd``). When the
    validator runs from an installed wheel inside a consumer repo, the
    source tree is not reachable and the function returns ``None`` —
    the test then ``pytest.skip``s rather than mis-asserting.
    """
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate_src_atdd = ancestor / "src" / "atdd"
        candidate_pyproject = ancestor / "pyproject.toml"
        if candidate_src_atdd.is_dir() and candidate_pyproject.is_file():
            return candidate_src_atdd
    return None


def is_editable_install(repo_src_atdd: Path | None) -> bool:
    """True iff the imported ``atdd`` package IS the source tree.

    When ``Path(atdd.__file__).resolve().parent`` is the repo's own
    ``src/atdd/`` directory, source == wheel-root and the wheel-
    completeness check is a tautology — skip rather than run.
    """
    if repo_src_atdd is None:
        return False
    installed_atdd_dir = Path(atdd.__file__).resolve().parent
    return installed_atdd_dir == repo_src_atdd.resolve()


# ---------------------------------------------------------------------------
# Source-tree inverse scan
# ---------------------------------------------------------------------------
def collect_source_fixture_files(repo_src_atdd: Path) -> List[Path]:
    """All files under any ``<phase>/validators/fixtures/`` tree.

    Cache-cruft is filtered out so the scan only considers files that
    are genuinely supposed to ship.
    """
    fixture_files: List[Path] = []
    for phase_dir in sorted(repo_src_atdd.iterdir()):
        if not phase_dir.is_dir():
            continue
        fixtures_root = phase_dir / "validators" / "fixtures"
        if not fixtures_root.is_dir():
            continue
        for path in fixtures_root.rglob("*"):
            if not path.is_file():
                continue
            if _is_cache_cruft(path):
                continue
            fixture_files.append(path)
    return fixture_files


def expected_install_path(
    src_path: Path, repo_src_atdd: Path, installed_atdd_dir: Path
) -> Path:
    """Map a source-tree fixture path to its expected install location."""
    relative = src_path.relative_to(repo_src_atdd)
    return installed_atdd_dir / relative


def find_missing_fixtures(
    source_files: Iterable[Path],
    repo_src_atdd: Path,
    installed_atdd_dir: Path,
) -> List[Tuple[Path, Path]]:
    """Return ``[(src_path, expected_install_path), ...]`` for every fixture
    file present in the source tree but missing from the installed wheel.
    """
    missing: List[Tuple[Path, Path]] = []
    for src in source_files:
        expected = expected_install_path(src, repo_src_atdd, installed_atdd_dir)
        if not expected.exists():
            missing.append((src, expected))
    return missing


# ---------------------------------------------------------------------------
# Violation construction
# ---------------------------------------------------------------------------
def build_violations(
    missing: Iterable[Tuple[Path, Path]],
    repo_src_atdd: Path,
) -> List[Violation]:
    """Translate ``(src, expected)`` pairs into ``Violation`` records."""
    violations: List[Violation] = []
    repo_root = repo_src_atdd.parent.parent  # <repo>/src/atdd → <repo>
    for src, expected in missing:
        try:
            location = str(src.relative_to(repo_root))
        except ValueError:
            location = str(src)
        detail = (
            f"fixture present in source tree but missing from installed "
            f"wheel: expected at {expected}. Check pyproject.toml "
            f"[tool.setuptools.package-data] glob and MANIFEST.in "
            f"recursive-exclude rules."
        )
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=f"{location}:1",
                detail=detail,
                fix_hint_ref="recipe:wheel-completeness#package-data",
            )
        )
    return violations


# ===========================================================================
# Tests
# ===========================================================================
@pytest.mark.coach
def test_validator_fixtures_present_in_wheel():
    """SPEC-COACH-WHEEL-COMPLETENESS-0001: every source-tree fixture ships in the wheel.

    Walks ``src/atdd/**/validators/fixtures/**`` (excluding cache-cruft)
    and asserts each file exists at the corresponding path under the
    installed atdd package directory. Skips cleanly on editable install
    (source == wheel root) or when no source tree is reachable
    (consumer-repo install).
    """
    repo_src_atdd = find_repo_src_atdd()
    if repo_src_atdd is None:
        pytest.skip(
            "no toolkit source tree reachable — wheel-completeness only "
            "meaningful when run from the toolkit repo"
        )

    if is_editable_install(repo_src_atdd):
        pytest.skip(
            "editable install — source tree IS the wheel root, "
            "wheel-completeness check is trivially satisfied"
        )

    source_files = collect_source_fixture_files(repo_src_atdd)
    if not source_files:
        pytest.skip("no validator fixtures found in source tree")

    installed_atdd_dir = Path(atdd.__file__).resolve().parent
    missing = find_missing_fixtures(
        source_files, repo_src_atdd, installed_atdd_dir
    )

    if missing:
        violations = build_violations(missing, repo_src_atdd)
        formatted = "\n".join(f"  {v}" for v in violations)
        pytest.fail(
            f"{len(missing)} validator fixture file(s) present in source "
            f"tree but missing from installed wheel "
            f"({installed_atdd_dir}):\n{formatted}\n"
            f"Convention: src/atdd/coach/conventions/"
            f"wheel-completeness.convention.yaml\n"
            f"Disposition: {_RULE.disposition} (3.7.x); promoted to "
            f"strict in 3.8.0."
        )
