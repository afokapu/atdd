# URN: test:validate-conventions:tune-convention-suite:E036-SMOKE-split-covers-the-whole-suite
# Acceptance: acc:validate-conventions:E036-SMOKE-001-split-collects-the-whole-suite
# Acceptance: acc:validate-conventions:E036-SMOKE-002-ci-runs-both-subsets-and-the-gate-fans-in-both
# WMBT: wmbt:validate-conventions:E036
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E036 SMOKE — the split is a partition, and CI actually runs both halves (#1418).

Two ways a marker-partitioned suite silently loses coverage, both closed here against the
real checkout and the real workflow file:

  E036-SMOKE-001  a test falls through BOTH ``-m`` filters (a third marker, a typo, a class
                  that stops being applied) and is simply never run again. The count the
                  green checkmark is standing behind quietly drops. So the two subsets are
                  collected through real ``python -m pytest`` and asserted to sum to the
                  un-split total, with neither half empty.

  E036-SMOKE-002  the split lands in ``pyproject.toml`` but CI keeps running the old single
                  command, or runs the new pair without teaching ``validate-gate`` to fan in
                  both — so a red serial subset never fails the gate. The workflow is parsed
                  and both halves are traced through to the gate's result check.

There is deliberately NO wall-clock assertion. CI wall-clock swings ±25% on identical code,
and the cheapest way to satisfy a timing gate is to run fewer tests — which points straight
at the fault-injection coverage Y003 exists to protect. The speedup is reported on the PR as
a measured number instead.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SERIAL_MARKER = "convention_filesystem_mutation"
PARALLEL_SELECTOR = f"not {SERIAL_MARKER}"
WORKFLOW = ".github/workflows/atdd-validate.yml"
PARALLEL_JOB = "validate-conventions"
SERIAL_JOB = "validate-conventions-serial"
GATE_JOB = "validate-gate"


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


def _collected(root: Path, *selector: str) -> int:
    """How many tests `python -m pytest --collect-only` selects — the number the CI job
    would actually execute. Read off the real collector, not re-derived from the markers,
    so a marker that stops being applied cannot hide inside our own bookkeeping."""
    conv = root / "src" / "atdd" / "validators" / "conventions"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(conv), "--collect-only", "-q",
         "-p", "no:cacheprovider", *selector],
        cwd=root, env=dict(os.environ), capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, (
        f"collection failed for selector {selector or '(none)'}:\n{result.stdout[-3000:]}"
    )
    # "232 tests collected in 1.2s", or "187/232 tests collected (45 deselected) in 1.2s"
    match = re.search(r"(\d+)(?:/\d+)? tests? collected", result.stdout)
    assert match, f"could not read a collected count from:\n{result.stdout[-2000:]}"
    return int(match.group(1))


@pytest.mark.convention_filesystem_mutation
def test_smoke_001_the_two_subsets_collect_the_whole_suite() -> None:
    """E036-SMOKE-001: parallel + serial == the un-split suite, and neither half is empty."""
    root = _repo_root()

    full = _collected(root)
    parallel = _collected(root, "-m", PARALLEL_SELECTOR)
    serial = _collected(root, "-m", SERIAL_MARKER)

    assert parallel + serial == full, (
        f"the marker split is NOT a partition: {parallel} parallel + {serial} serial != {full} "
        "collected un-split. Some test falls through both filters and is no longer run by any "
        "CI job — coverage was dropped, not parallelised."
    )
    assert serial > 0, (
        "no test is marked serial, which cannot be true while the loader fault families still "
        "write the tree — the marker has stopped being applied"
    )
    assert parallel > 0, "the parallel subset is empty — the split bought nothing"


@pytest.mark.convention_filesystem_mutation
def test_smoke_002_ci_runs_both_subsets_and_the_gate_fans_in_both() -> None:
    """E036-SMOKE-002: both jobs exist, select complementary halves, and reach validate-gate."""
    root = _repo_root()
    workflow = yaml.safe_load((root / WORKFLOW).read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    for name in (PARALLEL_JOB, SERIAL_JOB):
        assert name in jobs, f"{WORKFLOW} has no `{name}` job — a half of the suite never runs"

    def _run_steps(job: str) -> str:
        return "\n".join(step.get("run", "") for step in jobs[job]["steps"])

    parallel_steps = _run_steps(PARALLEL_JOB)
    serial_steps = _run_steps(SERIAL_JOB)

    assert f'-m "{PARALLEL_SELECTOR}"' in parallel_steps, (
        f"`{PARALLEL_JOB}` does not select the non-mutating half with -m \"{PARALLEL_SELECTOR}\""
    )
    assert "-n auto" in parallel_steps, (
        f"`{PARALLEL_JOB}` does not run under xdist — the whole point of the split is unrealised"
    )
    assert "pytest-xdist" in parallel_steps, (
        f"`{PARALLEL_JOB}` runs `-n auto` without installing pytest-xdist; the job's pip install "
        "is a bare list that does not read pyproject.toml, so the flag would be an unknown option"
    )
    assert f'-m "{SERIAL_MARKER}"' in serial_steps, (
        f"`{SERIAL_JOB}` does not select the mutating half with -m \"{SERIAL_MARKER}\""
    )
    assert "-n " not in serial_steps, (
        f"`{SERIAL_JOB}` runs under xdist — these are exactly the tests that share one checkout "
        "and must not"
    )

    gate = jobs[GATE_JOB]
    for name in (PARALLEL_JOB, SERIAL_JOB):
        assert name in gate["needs"], f"`{GATE_JOB}` does not wait on `{name}`"

    gate_checks = "\n".join(step.get("run", "") for step in gate["steps"])
    for name in (PARALLEL_JOB, SERIAL_JOB):
        assert f"needs.{name}.result" in gate_checks, (
            f"`{GATE_JOB}` waits on `{name}` but never reads its result — a red {name} would "
            "not fail the gate"
        )
