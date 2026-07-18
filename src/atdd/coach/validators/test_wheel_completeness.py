# URN: component:govern-lifecycle:enforcement-substrate:test_wheel_completeness:backend:domain
# Runtime: python
# Purpose: Build-time guard — every file in the src tree (minus cruft) must ship in the installed wheel.

"""Coach validator for wheel-completeness (issues #451, #1474).

Source-tree inverse scan, NOT code AST: walk every file under
``<repo_root>/src/atdd/`` (minus build/OS cruft) and assert each one exists at the
corresponding path under ``Path(atdd.__file__).resolve().parent``. The invariant is
blunt on purpose: **the installed package is the source tree minus cruft**.

Why an inverse scan rather than parsing validator code for the files it reads:
the AST approach is prone to false negatives on f-string / dynamic-path patterns
(``for bucket in (...): path = base / bucket / "harness_output.json"``). The
inverse scan walks the source tree directly and is impossible to confuse — there
is no parsing involved.

#1474 repaired three defects that between them meant this validator had never
executed a single assertion in any environment:

1. **It could not see.** The scan was confined to
   ``src/atdd/**/validators/fixtures/**``. Every directory that actually failed to
   ship was outside it: ``coach/schemas/*.md`` (#663), ``coder/conventions/nodes/``
   and ``tester/conventions/nodes/`` (#1369), ``coach/templates/bin/`` (#952). The
   scan now covers every file, minus an explicit deny-list that mirrors
   ``[tool.setuptools.exclude-package-data]``.

2. **It could not run.** Source-tree discovery walked the parents of this file's
   ``__file__``. From an installed wheel that finds no checkout (skip); from the
   source tree it finds one and concludes source == wheel root (skip). Discovery
   now falls back to the working directory, so the gate EXECUTES in the topology
   the ``validate-consumer`` CI job creates: package imported from site-packages,
   cwd at the toolkit checkout.

3. **It could not fail.** Its rule sat at ``disposition: advisory``, which logs a
   warning and passes. It is now ``strict``.

The one honest skip survives: under an editable install (or ``PYTHONPATH=src``) the
imported package IS the source tree, so every assertion is a file being compared to
itself. That is a tautology, not a check.

Convention: ``src/atdd/coach/conventions/wheel-completeness.convention.yaml``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import pytest

import atdd
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation


pytestmark = [pytest.mark.coach, pytest.mark.platform]


_RULE = bind_rule("coach.wheel-completeness.fixture-missing-from-wheel")
_VALIDATOR_ID = "wheel_completeness"


# ---------------------------------------------------------------------------
# The deny-list — mirrors [tool.setuptools.exclude-package-data] in pyproject.toml
# ---------------------------------------------------------------------------
# Build/OS cruft, and nothing else. The invariant the gate enforces is blunt on
# purpose: **the installed package is the source tree minus cruft**.
#
# Note that ``.py`` is NOT excluded. Most .py ship as importable MODULES, but the
# ones under ``**/validators/fixtures/**`` do not — ``packages.find``'s ``exclude``
# keeps those directories from being packages, so they ship as DATA (fixture sources
# validators read and parse) or not at all. A ``.py`` exclusion here would drop 21 of
# them, and the gate would be blind to it. Scanning every file sidesteps the
# module-or-data question entirely.
_EXCLUDED_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache"})
_EXCLUDED_SUFFIXES = (".pyc", ".pyo")
_EXCLUDED_FILE_NAMES = frozenset({".DS_Store"})


def is_excluded_from_package_data(path: Path) -> bool:
    """True iff *path* is deliberately NOT shipped in the installed package.

    Keep in step with ``[tool.setuptools.exclude-package-data]``: this predicate is
    the gate's model of that policy, and the two drifting apart is the failure this
    validator exists to catch.
    """
    if path.name in _EXCLUDED_FILE_NAMES:
        return True
    if path.suffix in _EXCLUDED_SUFFIXES:
        return True
    return any(part in _EXCLUDED_DIR_NAMES for part in path.parts)


# ---------------------------------------------------------------------------
# Repo-root + source-tree discovery
# ---------------------------------------------------------------------------
def find_repo_src_atdd(
    start: Optional[Path] = None, cwd: Optional[Path] = None
) -> Optional[Path]:
    """Return the toolkit's source-tree ``src/atdd`` path, or ``None``.

    Two probes, in order:

    1. Walk the parents of *start* (this file by default). Finds the checkout when
       the validator runs from the source tree.
    2. Walk the parents of *cwd*. Finds the checkout when the validator runs from an
       INSTALLED WHEEL while the working directory is the toolkit repo — which is
       the whole point: that is the only topology in which this gate has anything
       to say, and before #1474 probe 1 was the only probe, so the gate skipped.

    ``None`` (no checkout reachable at all) means the validator is running inside a
    consumer repo off an installed wheel. There is no source tree to compare
    against, so the caller skips rather than mis-asserting.
    """
    for origin in (start or Path(__file__).resolve(), cwd or Path.cwd().resolve()):
        for ancestor in (origin, *origin.parents):
            candidate = ancestor / "src" / "atdd"
            if candidate.is_dir() and (ancestor / "pyproject.toml").is_file():
                return candidate
    return None


def is_editable_install(repo_src_atdd: Path, installed_atdd_dir: Path) -> bool:
    """True iff the imported ``atdd`` package IS the source tree.

    Source == wheel root makes every ``expected.exists()`` a file compared to
    itself. The scan is a tautology and must short-circuit.
    """
    return installed_atdd_dir.resolve() == repo_src_atdd.resolve()


# ---------------------------------------------------------------------------
# Source-tree inverse scan
# ---------------------------------------------------------------------------
def collect_source_package_data_files(repo_src_atdd: Path) -> List[Path]:
    """Every file under ``src/atdd/`` that must be present in the installed package."""
    return sorted(
        path
        for path in repo_src_atdd.rglob("*")
        if path.is_file() and not is_excluded_from_package_data(path)
    )


def expected_install_path(
    src_path: Path, repo_src_atdd: Path, installed_atdd_dir: Path
) -> Path:
    """Map a source-tree data file to its expected location in the package."""
    return installed_atdd_dir / src_path.relative_to(repo_src_atdd)


def find_missing_package_data(
    source_files: Iterable[Path],
    repo_src_atdd: Path,
    installed_atdd_dir: Path,
) -> List[Tuple[Path, Path]]:
    """``[(src_path, expected_install_path), ...]`` for each file that did not ship."""
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
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=f"{location}:1",
                detail=(
                    f"present in the source tree but missing from the installed "
                    f"package: expected at {expected}. Shipped code reads this file "
                    f"at runtime, so a consumer install is broken without it. Check "
                    f"the pyproject.toml [tool.setuptools.package-data] broad-ship "
                    f"glob and the [tool.setuptools.exclude-package-data] deny-list."
                ),
                fix_hint_ref="recipe:wheel-completeness#package-data",
            )
        )
    return violations


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WheelCompletenessOutcome:
    """``pass`` | ``skip`` (with a reason) | ``fail`` (with violations)."""

    status: str
    reason: Optional[str] = None
    violations: List[Violation] = field(default_factory=list)


def evaluate_wheel_completeness(
    repo_src_atdd: Path, installed_atdd_dir: Path
) -> WheelCompletenessOutcome:
    """Compare the source tree's package-data set against the installed package.

    Pure over its two inputs, so the gate's own logic is testable without an actual
    wheel — which is what let the pre-#1474 version hide a scan that never ran.
    """
    if is_editable_install(repo_src_atdd, installed_atdd_dir):
        return WheelCompletenessOutcome(
            status="skip",
            reason=(
                "editable install — the source tree IS the package root, so every "
                "assertion compares a file to itself. CI's validate-consumer job "
                "exercises the wheel-built path."
            ),
        )

    source_files = collect_source_package_data_files(repo_src_atdd)
    if not source_files:
        return WheelCompletenessOutcome(
            status="skip", reason="no package-data files found in the source tree"
        )

    missing = find_missing_package_data(source_files, repo_src_atdd, installed_atdd_dir)
    if missing:
        return WheelCompletenessOutcome(
            status="fail", violations=build_violations(missing, repo_src_atdd)
        )
    return WheelCompletenessOutcome(status="pass")


# ===========================================================================
# Test
# ===========================================================================
@pytest.mark.coach
def test_validator_fixtures_present_in_wheel():
    """SPEC-COACH-WHEEL-COMPLETENESS-0001: every source data file ships in the wheel.

    Walks every file under ``src/atdd/`` (minus the cruft deny-list) and asserts
    each exists under the installed ``atdd`` package directory.

    Runs for real whenever the imported package is a wheel and the toolkit checkout
    is reachable — the `validate-consumer` CI job creates exactly that. Skips only
    on an editable install (a tautology) or in a consumer repo with no source tree
    to compare against.
    """
    repo_src_atdd = find_repo_src_atdd()
    if repo_src_atdd is None:
        pytest.skip(
            "no toolkit source tree reachable — wheel-completeness is only "
            "meaningful when the toolkit repo is available to compare against"
        )

    installed_atdd_dir = Path(atdd.__file__).resolve().parent
    outcome = evaluate_wheel_completeness(repo_src_atdd, installed_atdd_dir)

    if outcome.status == "skip":
        pytest.skip(outcome.reason or "wheel-completeness check not applicable")

    assert_disposition_satisfied(
        validator_id=_VALIDATOR_ID, violations=outcome.violations
    )
