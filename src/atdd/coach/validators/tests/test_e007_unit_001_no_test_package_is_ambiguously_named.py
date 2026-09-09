# URN: test:govern-lifecycle:govern-lifecycle:E007-UNIT-001-no-test-package-is-ambiguously-named
# Acceptance: acc:govern-lifecycle:E007-UNIT-001-no-test-package-is-ambiguously-named
# WMBT: wmbt:govern-lifecycle:E007
# Phase: RED
# Layer: application
"""E007-UNIT-001 — no test package may be named under the top-level `tests`.

Enumerates the tree rather than naming the two directories that are broken today.
A third such directory added later would silently re-open the 25-error wall, and
the next reader would have no way to know why the suite stopped collecting.

Structural, not behavioural: it reproduces the rule pytest uses to name a module
(walk up to the first directory without ``__init__.py``) instead of shelling out,
so it is fast enough to run in the ordinary suite and states the invariant in the
same terms the failure will be reported in.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo

_PKG_MARKER = "__init__.py"


def _module_root(directory: Path) -> Path:
    """The directory pytest would treat as the import root for files in *directory*."""
    root = directory
    while (root.parent / _PKG_MARKER).exists():
        root = root.parent
    return root


@pytest.mark.coder
@pytest.mark.platform
def test_no_tests_package_sits_under_a_non_package_parent():
    if not is_atdd_source_repo():
        pytest.skip("structural check over this repository's own source tree")

    src = Path(find_repo_root()) / "src"
    offenders = []

    for directory in sorted(src.rglob("tests")):
        if not directory.is_dir():
            continue
        if not (directory / _PKG_MARKER).exists():
            # No package marker: named rootdir-relative, does not contend for `tests`.
            continue
        if (directory.parent / _PKG_MARKER).exists():
            continue
        offenders.append(directory.relative_to(src).as_posix())

    assert not offenders, (
        "these are packages whose parent is not, so pytest names their modules "
        f"under the top-level `tests` namespace and they collide with the root "
        f"tests/ package: {offenders}. Add an {_PKG_MARKER} to each parent."
    )


@pytest.mark.coder
@pytest.mark.platform
def test_the_check_would_notice_a_newly_added_offender(tmp_path):
    """Non-vacuity: the rule must actually fire on the shape it forbids."""
    victim = tmp_path / "not_a_package" / "tests"
    victim.mkdir(parents=True)
    (victim / _PKG_MARKER).touch()

    assert _module_root(victim) == victim, (
        "with a non-package parent the import root is the tests dir itself, which "
        "is what names its modules `tests.*`"
    )

    (victim.parent / _PKG_MARKER).touch()
    assert _module_root(victim) == victim.parent, (
        "once the parent is a package the walk continues, and the modules are "
        "named under it instead"
    )
