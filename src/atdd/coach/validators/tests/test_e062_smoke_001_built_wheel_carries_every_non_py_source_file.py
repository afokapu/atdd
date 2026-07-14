# URN: test:govern-lifecycle:ship-package-data-and-consumer-ci:E062-SMOKE-001-built-wheel-carries-every-non-py-source-file
# Acceptance: acc:govern-lifecycle:E062-SMOKE-001-built-wheel-carries-every-non-py-source-file
# WMBT: wmbt:govern-lifecycle:E062
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""E062-SMOKE-001 — the wheel a consumer installs carries every file shipped code reads.

Real infra: a genuine ``python -m build --wheel`` over the repo checkout, driven
through the real in-tree PEP-517 backend, with the resulting wheel opened and its
member list read. This asserts against the artifact consumers actually install
rather than against the glob text in ``pyproject.toml`` — the glob text is what
was wrong, so reading it back would prove nothing.

Three claims, because the fix has three ways to go wrong:
  * every non-.py source file ships          — the bug (#663/#952/#1369): 174 absent
  * every .py module still ships             — the deny-list's ``**/*.py`` entry
                                               suppresses .py as *data*; setuptools
                                               must still install it as a *module*
  * no build cruft ships                     — the broad ``**/*`` glob must not
                                               sweep in __pycache__/*.pyc/.DS_Store
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.validators.test_wheel_completeness import is_excluded_from_package_data

from ._wheel_harness import built_wheel, repo_root, wheel_members

pytestmark = [pytest.mark.coach]


def _source_data_files(src_atdd: Path) -> set[str]:
    """Every non-.py, non-excluded file under src/atdd/, as `atdd/...` paths."""
    return {
        f"atdd/{path.relative_to(src_atdd).as_posix()}"
        for path in src_atdd.rglob("*")
        if path.is_file() and not is_excluded_from_package_data(path)
    }


@pytest.mark.smoke
def test_e062_smoke_001_built_wheel_carries_every_non_py_source_file():
    src_atdd = repo_root() / "src" / "atdd"
    members = wheel_members()

    missing = sorted(_source_data_files(src_atdd) - members)
    assert not missing, (
        f"{len(missing)} non-.py source file(s) that shipped code reads are absent "
        f"from the built wheel ({built_wheel().name}). This is the #663/#952/#1369 "
        f"root cause: `[tool.setuptools.package-data]` did not glob them in.\n"
        + "\n".join(f"  {m}" for m in missing[:25])
        + (f"\n  ... and {len(missing) - 25} more" if len(missing) > 25 else "")
    )


@pytest.mark.smoke
def test_e062_smoke_001_deny_list_does_not_suppress_py_modules():
    """The `**/*.py` deny-list entry must filter .py as DATA, never as a MODULE.

    `exclude-package-data` feeds setuptools' data-file copier only; modules are
    installed by a separate code path. If that ever stopped being true, the wheel
    would ship with no Python in it at all — so pin it.
    """
    src_atdd = repo_root() / "src" / "atdd"
    source_modules = {
        f"atdd/{p.relative_to(src_atdd).as_posix()}"
        for p in src_atdd.rglob("*.py")
        if "__pycache__" not in p.parts
    }
    missing = sorted(source_modules - wheel_members())

    assert source_modules, "no .py modules found in the source tree — scan is broken"
    assert not missing, (
        f"{len(missing)} .py module(s) are missing from the wheel — the "
        f"exclude-package-data deny-list has suppressed modules, not just data:\n"
        + "\n".join(f"  {m}" for m in missing[:15])
    )


@pytest.mark.smoke
def test_e062_smoke_001_wheel_carries_no_build_cruft():
    """The broad `**/*` glob must not sweep byte-code or OS cruft into the wheel."""
    cruft = sorted(
        m for m in wheel_members()
        if "__pycache__" in m
        or m.endswith((".pyc", ".pyo"))
        or m.endswith(".DS_Store")
    )
    assert not cruft, (
        "the built wheel carries build/OS cruft — the broad-ship glob is not "
        "correctly fenced by exclude-package-data:\n"
        + "\n".join(f"  {c}" for c in cruft[:15])
    )
