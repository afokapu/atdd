# URN: test:govern-lifecycle:ship-package-data-and-consumer-ci:C008-UNIT-001-scan-covers-every-non-py-package-file
# Acceptance: acc:govern-lifecycle:C008-UNIT-001-scan-covers-every-non-py-package-file
# WMBT: wmbt:govern-lifecycle:C008
# Phase: GREEN
# Layer: backend.domain
# Assertion: behavioral
"""C008-UNIT-001 — the wheel-completeness scan sees the files that actually broke.

The #451 gate scanned only ``src/atdd/**/validators/fixtures/**``. Every directory
that actually failed to ship — ``coach/schemas/*.md`` (#663),
``coder/conventions/nodes/`` (#1369), ``coach/templates/bin/`` (#952) — was outside
that glob, so even a gate that ran could not have caught any of them.

The scan must now collect every file, minus build/OS cruft — which the deny-list
keeps out of the wheel on purpose, so asserting it shipped would fail the gate on a
file that is right to be absent.

``.py`` is deliberately IN scope. The obvious-looking alternative (skip .py, since
setuptools installs it as a module anyway) is wrong: the .py under
``**/validators/fixtures/**`` are not modules — ``packages.find``'s ``exclude`` keeps
those directories from being importable — so they ship as DATA or not at all. A .py
exclusion drops 21 of them and blinds the gate to the loss.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.validators.test_wheel_completeness import (
    collect_source_package_data_files,
)

# `platform` marks this a TOOLKIT-SELF test: it needs the toolkit checkout (and/or a
# wheel built from it), which a consumer repo does not have. `atdd validate <phase>`
# adds `-m "not platform"` outside the source repo (E025), so this is deselected there
# and runs here. Without the marker these ship in the wheel and ERROR in every
# consumer's sweep — the #954 self-test-leak pathology, which this issue must not add to.
pytestmark = [pytest.mark.coach, pytest.mark.platform]


@pytest.fixture()
def synthetic_src_atdd(tmp_path: Path) -> Path:
    """A source tree carrying one file of each kind the scan must judge."""
    src_atdd = tmp_path / "src" / "atdd"
    files = [
        # the only kind the old scan could see
        "coder/validators/fixtures/stub/harness_output.json",
        # the kinds that actually broke, all previously invisible
        "coach/schemas/runtime-layout.md",
        "coder/conventions/nodes/coder.dead-code.reachability.convention.yaml",
        "tester/conventions/nodes/tester.contract.schema.convention.yaml",
        "coach/templates/bin/gh.shim",
        "coach/templates/persona/claude-code/CLAUDE.md.tmpl",
        "validators/conventions/registry.yaml",
        # a .py that IS a module
        "coach/commands/issue.py",
        # a .py that is NOT a module — fixtures/ is excluded from packages.find, so
        # this ships as data or not at all
        "coder/validators/fixtures/stub_presentation/component.py",
        # must NOT be collected: correctly excluded from the wheel
        "coach/commands/__pycache__/issue.cpython-312.pyc",
        "coach/schemas/.DS_Store",
    ]
    for rel in files:
        path = src_atdd / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    return src_atdd


def test_c008_unit_001_scan_collects_data_files_beyond_validator_fixtures(
    synthetic_src_atdd: Path,
):
    collected = {
        p.relative_to(synthetic_src_atdd).as_posix()
        for p in collect_source_package_data_files(synthetic_src_atdd)
    }

    must_collect = {
        "coder/validators/fixtures/stub/harness_output.json",
        "coach/schemas/runtime-layout.md",
        "coder/conventions/nodes/coder.dead-code.reachability.convention.yaml",
        "tester/conventions/nodes/tester.contract.schema.convention.yaml",
        "coach/templates/bin/gh.shim",
        "coach/templates/persona/claude-code/CLAUDE.md.tmpl",
        "validators/conventions/registry.yaml",
    }
    assert must_collect <= collected, (
        "the scan is still blind to the directories that actually failed to ship; "
        f"missed: {sorted(must_collect - collected)}"
    )


def test_c008_unit_001_scan_collects_py_including_non_module_fixture_sources(
    synthetic_src_atdd: Path,
):
    """`.py` is in scope — a fixture `.py` is package DATA, and can go missing."""
    collected = {
        p.relative_to(synthetic_src_atdd).as_posix()
        for p in collect_source_package_data_files(synthetic_src_atdd)
    }

    assert "coder/validators/fixtures/stub_presentation/component.py" in collected, (
        "the scan skipped a .py under validators/fixtures/. Those directories are "
        "excluded from packages.find, so nothing installs them as modules — they are "
        "DATA. Skipping .py wholesale drops 21 such files and blinds the gate to it."
    )
    assert "coach/commands/issue.py" in collected, (
        "the scan skipped a module .py. The gate asserts the installed package is the "
        "source tree minus cruft, and a module absent from the package is a real "
        "failure — there is no reason to exempt it"
    )


def test_c008_unit_001_scan_excludes_build_cruft(synthetic_src_atdd: Path):
    collected = {
        p.relative_to(synthetic_src_atdd).as_posix()
        for p in collect_source_package_data_files(synthetic_src_atdd)
    }

    must_not_collect = {
        "coach/commands/__pycache__/issue.cpython-312.pyc",
        "coach/schemas/.DS_Store",
    }
    assert not (must_not_collect & collected), (
        "the scan collected build/OS cruft, which must NOT ship — asserting it exists "
        "in the wheel would fail the gate on files that are correctly absent; wrongly "
        f"collected: {sorted(must_not_collect & collected)}"
    )
