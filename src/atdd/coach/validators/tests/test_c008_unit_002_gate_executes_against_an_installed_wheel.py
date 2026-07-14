# URN: test:govern-lifecycle:ship-package-data-and-consumer-ci:C008-UNIT-002-gate-executes-against-an-installed-wheel-instead-of-skipping
# Acceptance: acc:govern-lifecycle:C008-UNIT-002-gate-executes-against-an-installed-wheel-instead-of-skipping
# WMBT: wmbt:govern-lifecycle:C008
# Phase: GREEN
# Layer: backend.domain
# Assertion: behavioral
"""C008-UNIT-002 — the gate EXECUTES against an installed wheel instead of skipping.

``find_repo_src_atdd()`` walked the parents of its own ``__file__``. From an
installed wheel that walk finds no checkout, so the gate skipped — and from the
source tree it found one, decided source == wheel root, and skipped again. There
was no environment left in which it ran.

Source-tree discovery must therefore fall back to the working directory: when the
imported ``atdd`` lives in site-packages but the toolkit repo IS the cwd — exactly
the topology the new ``validate-consumer`` CI job creates — the gate resolves the
checkout, runs, and FAILS on a data file that did not ship.

The third assertion is the anti-vacuity control: the same package root WITH the
file must pass, so the failure above is attributable to the missing file and not
to the discovery change having broken something.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.validators.test_wheel_completeness import (
    evaluate_wheel_completeness,
    find_repo_src_atdd,
)

pytestmark = [pytest.mark.coach]

_DATA_REL = "coder/conventions/nodes/coder.dead-code.reachability.convention.yaml"


@pytest.fixture()
def synthetic_checkout(tmp_path: Path) -> Path:
    """A toolkit checkout that is NOT an ancestor of the imported package."""
    root = tmp_path / "checkout"
    (root / "src" / "atdd").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'atdd'\n")
    data = root / "src" / "atdd" / _DATA_REL
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text("rule_id: coder.dead-code.reachability\n")
    return root


def _package_root(tmp_path: Path, *, carrying_data: bool) -> Path:
    """A site-packages-shaped `atdd/` directory, with or without the data file."""
    name = "complete" if carrying_data else "incomplete"
    pkg = tmp_path / name / "atdd"
    (pkg / "coach").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    if carrying_data:
        data = pkg / _DATA_REL
        data.parent.mkdir(parents=True, exist_ok=True)
        data.write_text("rule_id: coder.dead-code.reachability\n")
    return pkg


def test_c008_unit_002_discovery_falls_back_to_the_working_directory(
    synthetic_checkout: Path, monkeypatch: pytest.MonkeyPatch
):
    """From a wheel install, the checkout is found via cwd — not via __file__."""
    monkeypatch.chdir(synthetic_checkout)

    found = find_repo_src_atdd(start=Path("/nonexistent/site-packages/atdd/coach"))

    assert found == synthetic_checkout / "src" / "atdd", (
        "source-tree discovery did not fall back to the working directory. From an "
        "installed wheel the __file__ walk finds no checkout, so without this "
        "fallback the gate skips — which is why it has never run."
    )


def test_c008_unit_002_gate_fails_on_a_data_file_missing_from_the_package(
    synthetic_checkout: Path, tmp_path: Path
):
    outcome = evaluate_wheel_completeness(
        repo_src_atdd=synthetic_checkout / "src" / "atdd",
        installed_atdd_dir=_package_root(tmp_path, carrying_data=False),
    )

    assert outcome.status == "fail", (
        f"the gate returned {outcome.status!r} for a package root that is missing a "
        f"shipped data file. It must FAIL, not skip — a gate that skips here is the "
        f"#451 defect this issue repairs. Reason: {outcome.reason!r}"
    )
    detail = "\n".join(str(v) for v in outcome.violations)
    assert _DATA_REL in detail, (
        f"the failure does not name the missing file, so an operator cannot act on "
        f"it:\n{detail}"
    )
    assert "package-data" in detail, (
        f"the failure does not point at the pyproject policy that must ship the "
        f"file:\n{detail}"
    )


def test_c008_unit_002_gate_passes_when_the_package_carries_the_file(
    synthetic_checkout: Path, tmp_path: Path
):
    """Anti-vacuity control: the failure above is the missing file, not the plumbing."""
    outcome = evaluate_wheel_completeness(
        repo_src_atdd=synthetic_checkout / "src" / "atdd",
        installed_atdd_dir=_package_root(tmp_path, carrying_data=True),
    )

    assert outcome.status == "pass", (
        f"the gate did not pass against a COMPLETE package root — the missing-file "
        f"failure is not attributable to the missing file. status={outcome.status!r} "
        f"reason={outcome.reason!r} violations={[str(v) for v in outcome.violations]}"
    )
