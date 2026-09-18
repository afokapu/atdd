# URN: test:author-atdd-substrate:definition-anchor:C016-SMOKE-001-definition-drift-is-caught-live
# Acceptance: acc:author-atdd-substrate:C016-SMOKE-001-definition-drift-is-caught-live
# WMBT: wmbt:author-atdd-substrate:C016
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the shipped planner validator passes over this repository's real convention nodes, and REFUSES a node seeded with an unsupported field claim, naming the node and the claim. Plus: the corrected WMBT scanner counts all nine step codes. Refs #2039.
"""SMOKE — definition drift is caught by the shipped gate (C016-SMOKE-001).

wagon: author-atdd-substrate | feature: author-convention-node | phase: SMOKE
WMBT: wmbt:author-atdd-substrate:C016

A guard nobody has seen fail is a guard nobody has tested. The unit acceptances
assert the scan's verdict in-process; this one drives the real validator by
subprocess against the real corpus, then **seeds a drift and watches it bite** —
because the failure this issue exists to prevent is a definition that quietly
stops describing its artifact, and a check that only ever passes would be
indistinguishable from no check at all.

The third assertion covers the scanner the same drift had corrupted: `atdd coach
inventory`'s WMBT count was wrong by 31% because its category table was an
invention, and a hand-fix without a regression guard would let the next step
letter re-drift silently.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.smoke, pytest.mark.platform]

REPO = find_repo_root()
VALIDATOR = "src/atdd/planner/validators/test_definition_claims_resolve.py"
NODES = REPO / "src" / "atdd" / "planner" / "conventions" / "nodes"

#: The nine JTBD step codes, as wmbt.schema.json's `step` enum declares them.
STEP_CODES = ("D", "L", "P", "C", "E", "M", "Y", "R", "K")


def _run_validator() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", VALIDATOR, "-q", "--tb=short", "-p", "no:cacheprovider"],
        cwd=str(REPO), capture_output=True, text=True, timeout=300,
    )


@pytest.mark.smoke
def test_c016_smoke_001_the_real_corpus_passes() -> None:
    """The shipped validator is clean over this repository's own convention nodes."""
    result = _run_validator()
    assert result.returncode == 0, (
        "planner.definition.claims-must-resolve reports drift on the real corpus.\n"
        f"stdout:\n{result.stdout[-4000:]}\nstderr:\n{result.stderr[-800:]}"
    )


@pytest.mark.smoke
def test_c016_smoke_001_seeded_drift_is_refused(tmp_path) -> None:
    """Seed a field claim no authority supports; the shipped gate must name it.

    The seed is written into the real node and removed in `finally`, because the
    validator reads the committed tree — a copy under tmp_path would prove the
    check runs, not that it runs against what ships.
    """
    node = NODES / "planner.wagon.definition.convention.yaml"
    original = node.read_text(encoding="utf-8")
    anchor = "statement: A wagon is a separable"
    assert anchor in original, "the wagon anchor's statement shape changed; reseed this test"
    seeded = original.replace(
        anchor,
        "statement: A wagon declares a `nonexistent_field` that no authority supports. "
        "A wagon is a separable",
        1,
    )
    assert seeded != original

    try:
        node.write_text(seeded, encoding="utf-8")
        result = _run_validator()
        combined = result.stdout + result.stderr
        assert result.returncode != 0, (
            f"the seeded drift was NOT refused — the gate passed a node asserting a field "
            f"no authority declares:\n{combined[-3000:]}"
        )
        assert "nonexistent_field" in combined, (
            f"the refusal does not name the unsupported claim:\n{combined[-3000:]}"
        )
        assert "planner.wagon.definition" in combined, (
            f"the refusal does not name the offending node:\n{combined[-3000:]}"
        )
    finally:
        node.write_text(original, encoding="utf-8")

    # The tree is restored, so the gate is clean again — a seed that leaked would
    # red-line every later run and look like a real defect.
    assert node.read_text(encoding="utf-8") == original
    assert _run_validator().returncode == 0, "the seed leaked; the corpus is no longer clean"


@pytest.mark.smoke
def test_c016_smoke_001_inventory_counts_every_step_code() -> None:
    """The corrected scanner knows all nine steps, not the four it used to invent."""
    from atdd.coach.commands.inventory import RepositoryInventory  # noqa: PLC0415

    result = RepositoryInventory(REPO).scan_wmbts()

    assert set(result["by_step"]) == {
        "define", "locate", "prepare", "confirm", "execute",
        "monitor", "modify", "resolve", "conclude",
    }, f"the scanner does not know the nine JTBD steps: {sorted(result['by_step'])}"

    on_disk = sum(
        len(list((REPO / "plan").glob(f"**/{code}[0-9]*.yaml"))) for code in STEP_CODES
    )
    assert result["total"] == on_disk, (
        f"the scanner counts {result['total']} WMBTs; {on_disk} step-coded files are on disk"
    )
    # The four codes it used to know must still be counted, and the five it did not
    # must now be non-zero — that is the 31% it was missing.
    for step in ("define", "monitor", "modify", "resolve", "conclude"):
        assert result["by_step"][step] > 0, f"{step!r} counted zero — the undercount is back"
