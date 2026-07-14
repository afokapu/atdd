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

The scan must now collect every non-.py file, and must NOT collect the two things
that correctly never ship: ``.py`` (installed as a module, not as data) and build
cruft (which the deny-list keeps out of the wheel on purpose — asserting it ships
would fail the gate on a file that is right to be absent).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.validators.test_wheel_completeness import (
    collect_source_package_data_files,
)

pytestmark = [pytest.mark.coach]


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
        # must NOT be collected: shipped as a module, not as data
        "coach/commands/issue.py",
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


def test_c008_unit_001_scan_excludes_py_modules_and_build_cruft(
    synthetic_src_atdd: Path,
):
    collected = {
        p.relative_to(synthetic_src_atdd).as_posix()
        for p in collect_source_package_data_files(synthetic_src_atdd)
    }

    must_not_collect = {
        "coach/commands/issue.py",
        "coach/commands/__pycache__/issue.cpython-312.pyc",
        "coach/schemas/.DS_Store",
    }
    assert not (must_not_collect & collected), (
        "the scan collected files that must NOT ship as package data — asserting "
        "they exist in the wheel would fail the gate on files that are correctly "
        f"absent; wrongly collected: {sorted(must_not_collect & collected)}"
    )
