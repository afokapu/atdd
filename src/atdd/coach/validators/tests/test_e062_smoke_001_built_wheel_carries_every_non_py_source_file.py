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
def test_e062_smoke_001_every_py_ships_including_non_module_fixture_sources():
    """Every `.py` ships — the module ones AND the fixture ones.

    The tempting deny-list entry `**/*.py` ("setuptools installs modules anyway")
    silently drops 21 files: the `.py` under `**/validators/fixtures/**` are NOT
    modules. `[tool.setuptools.packages.find] exclude` keeps those directories from
    being importable packages, so nothing installs them as code — they ship as DATA
    or not at all.

    Both classes are asserted together, because the whole point of the broad-ship
    policy is that the packaging config never has to answer "is this .py a module or
    data?" correctly.
    """
    src_atdd = repo_root() / "src" / "atdd"
    source_py = {
        f"atdd/{p.relative_to(src_atdd).as_posix()}"
        for p in src_atdd.rglob("*.py")
        if "__pycache__" not in p.parts
    }
    fixture_py = {m for m in source_py if "/validators/fixtures/" in m}

    assert source_py, "no .py found in the source tree — scan is broken"
    assert fixture_py, (
        "no .py found under validators/fixtures/ — the non-module .py class this test "
        "exists to protect has vanished, so the test is now vacuous"
    )

    missing = sorted(source_py - wheel_members())
    assert not missing, (
        f"{len(missing)} .py file(s) are missing from the wheel "
        f"({len([m for m in missing if '/validators/fixtures/' in m])} of them fixture "
        f"sources, which ship as data and have no module code path to fall back on):\n"
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
