# URN: test:validate-conventions:tune-convention-suite:E032-SMOKE-001-session-graph-in-real-checkout
# Acceptance: acc:validate-conventions:E032-SMOKE-001-session-graph-in-real-checkout
# WMBT: wmbt:validate-conventions:E032
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E032 SMOKE — the session graph holds through the real pytest entrypoint (#1414).

Exercises a real checkout through real ``python -m pytest`` subprocesses, no import-time
shortcuts, and asserts the three observable outcomes of E032-SMOKE-001:

  * the conventions suite still collects at least its pre-change test count (no test was
    deleted, skipped or xfailed to buy speed),
  * the counted invocations of ``load_composed_graph`` over the read-only suite collapse
    to exactly one,
  * the Y003 coverage-preserved guards remain green.

Deliberately NOT re-running all 218 tests in a child: this module is collected BY that
suite, so a full child run would double the very CI wall-clock #1397 exists to cut (and
nest a subprocess inside a subprocess). The parent CI invocation is what proves the full
suite exits 0; re-asserting it from within is circular. Full-suite build counts and
runtime are reported as measured numbers on the PR, never asserted — CI wall-clock swings
±25% on identical code.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

COUNTER_PLUGIN = "atdd.validators.conventions.tests.graph_build_counter"

# `pytest -q --collect-only` on b6a42f17, before this issue added its own gates.
PRE_CHANGE_TEST_COUNT = 218

Y003_GUARDS = "tests/test_y003_sweep_coverage_guards.py"


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


def _conventions_dir(root: Path) -> Path:
    return root / "src" / "atdd" / "validators" / "conventions"


def _pytest(root: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
        cwd=root, env=env or dict(os.environ),
        capture_output=True, text=True, timeout=900,
    )


@pytest.mark.convention_filesystem_mutation
def test_real_checkout_collects_the_full_suite() -> None:
    """No coverage was traded for speed: the suite still collects every test it had."""
    root = _repo_root()
    result = _pytest(root, str(_conventions_dir(root)), "-q", "--collect-only")
    assert result.returncode == 0, f"collection failed:\n{result.stdout[-3000:]}"

    match = re.search(r"(\d+)\s+tests?\s+collected", result.stdout)
    assert match, f"could not read the collected count from:\n{result.stdout[-2000:]}"
    collected = int(match.group(1))

    assert collected >= PRE_CHANGE_TEST_COUNT, (
        f"the conventions suite collects {collected} tests, down from "
        f"{PRE_CHANGE_TEST_COUNT} before #1414 — coverage was dropped, not sped up"
    )


@pytest.mark.convention_filesystem_mutation
def test_real_checkout_composes_the_graph_once(tmp_path: Path) -> None:
    """Through the real entrypoint, the read-only suite composes the graph exactly once."""
    root = _repo_root()
    count_file = tmp_path / "graph_builds.json"
    env = dict(os.environ)
    env["ATDD_GRAPH_BUILD_COUNT_FILE"] = str(count_file)

    result = _pytest(
        root, str(_conventions_dir(root)), "-k", "baseline", "-q", "-p", COUNTER_PLUGIN,
        env=env,
    )
    assert result.returncode == 0, f"read-only suite is red:\n{result.stdout[-3000:]}"

    stats = json.loads(count_file.read_text(encoding="utf-8"))
    assert stats["selected"] >= 30, f"vacuous: only {stats['selected']} read-only tests ran"
    assert stats["builds"] == 1, (
        f"real checkout composed the clean graph {stats['builds']}x, expected exactly 1"
    )


@pytest.mark.convention_filesystem_mutation
def test_y003_coverage_guards_stay_green() -> None:
    """The sweep's permanent coverage guards must survive the perf work."""
    root = _repo_root()
    result = _pytest(root, str(_conventions_dir(root) / Y003_GUARDS), "-q")
    assert result.returncode == 0, (
        f"Y003 coverage-preserved guards are red:\n{result.stdout[-3000:]}"
    )
