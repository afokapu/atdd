# URN: test:validate-conventions:tune-convention-suite:E035-SMOKE-001-no-file-written-in-real-checkout
# Acceptance: acc:validate-conventions:E035-GREEN-002-migrated-families-compose-the-graph-once
# Acceptance: acc:validate-conventions:E035-SMOKE-001-no-file-written-in-real-checkout
# WMBT: wmbt:validate-conventions:E035
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E035 SMOKE — the last seven fault families write nothing and rebuild nothing (#1458).

Exercises a real checkout through real ``python -m pytest`` over the seven families this
issue migrated and asserts the three observable outcomes:

  * the suite exits 0 (every migrated fault + baseline test passes),
  * ``git status`` reports no new modification to ANY tracked file. E034's guard globbed
    convention + plan YAML, which is the surface ITS five families wrote. These seven
    wrote git hooks, ``pyproject.toml``, ``src/atdd/*.py`` and a committed SMOKE test —
    none of which a YAML glob matches — so the guard here is the whole tracked tree,
  * the clean graph is composed EXACTLY ONCE across all seven families (the session
    fixture), because no fault test rebuilds it any more; and the fault tests are still
    selected, so that count is not bought by deselecting them.

Runtime is reported as a measured number on the PR, never asserted — CI wall-clock swings
too much to gate on, and a timing budget is cheapest to satisfy by deleting the very fault
coverage this suite exists to protect.
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

MIGRATED_FAMILIES = [
    "policy", "schema", "grammar", "composition", "boundary", "sizing", "uniqueness",
]
FAULT_SELECTOR = "fault or inject or catches_injected"
# The verified roster at migration: exactly one name-matched fault test in each of the 10
# fault-injecting files — policy 4 (bypass, freedom-layer, stale-suppression, smoke-
# synthetic), schema 1, grammar 1, composition 1, boundary 1, sizing 2. A lower count
# means a fault test was deleted or the selector stopped matching, and the speedup was
# bought with coverage. (schema's and composition's evidence-keys tests also inject a
# fault but are not name-matched; they are a bonus, not part of the floor.)
MIN_FAULT_TESTS = 10


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


def _family_dirs(root: Path) -> list[str]:
    base = root / "src" / "atdd" / "validators" / "conventions"
    return [str(base / fam) for fam in MIGRATED_FAMILIES]


def _tracked_status(root: Path) -> str:
    """`git status --porcelain` over the whole tracked tree — every surface the migrated
    families used to rewrite, not just the YAML ones."""
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=root, capture_output=True, text=True, timeout=120,
    )
    return result.stdout


@pytest.fixture(scope="module")
def migrated_family_run(tmp_path_factory) -> dict:
    """Run the seven migrated families ONCE, under the build counter, and capture
    everything the three acceptances below assert on.

    Deliberately a single subprocess. The obvious shape — one pytest run per assertion —
    re-executes all seven families three times, which cost 64.8s and handed back most of
    the time the migration had just saved. The suite's own gate must not be the thing
    that makes the suite slow. One run yields the exit status, the tracked-tree delta
    and the build count together, and each acceptance reads its own field off it.
    """
    root = _repo_root()
    count_file = tmp_path_factory.mktemp("e035") / "graph_builds.json"
    env = dict(os.environ)
    env["ATDD_GRAPH_BUILD_COUNT_FILE"] = str(count_file)

    before = _tracked_status(root)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *_family_dirs(root),
         "-q", "-p", "no:cacheprovider", "-p", COUNTER_PLUGIN],
        cwd=root, env=env, capture_output=True, text=True, timeout=900,
    )
    after = _tracked_status(root)

    stats = json.loads(count_file.read_text(encoding="utf-8")) if count_file.exists() else None
    return {
        "returncode": result.returncode, "stdout": result.stdout,
        "before": before, "after": after, "stats": stats,
    }


def test_migrated_families_are_green(migrated_family_run) -> None:
    run = migrated_family_run
    assert run["returncode"] == 0, f"a migrated family is red:\n{run['stdout'][-3000:]}"


def test_migrated_families_leave_the_checkout_untouched(migrated_family_run) -> None:
    run = migrated_family_run
    assert run["after"] == run["before"], (
        "the migrated fault families modified a tracked file — every fault is supposed to "
        "be staged under tmp_path or injected into a cloned graph, so the checkout must "
        f"never be written. git status delta:\n{run['after']}"
    )


def test_migrated_families_compose_the_clean_graph_once(migrated_family_run) -> None:
    """E035-GREEN-002: one real-root graph build across all seven families.

    The counter counts only builds rooted at the REAL repo root, so boundary's synthetic
    fixture graphs (composed over their own temp trees, and effectively free) are
    correctly not counted. What must be 1 is the CLEAN graph — the expensive one, which
    walks plan/ and every convention YAML.
    """
    stats = migrated_family_run["stats"]
    assert stats is not None, (
        f"counter plugin wrote no count:\n{migrated_family_run['stdout'][-2000:]}"
    )
    assert stats["builds"] == 1, (
        f"the clean convention graph was composed {stats['builds']}x across the seven "
        "migrated families; only the session fixture may compose it. A fault test is "
        "rebuilding the real graph again."
    )


def test_migrated_faults_are_still_caught(migrated_family_run) -> None:
    """Coverage preserved: the build count must not have been bought by deleting the
    fault tests.

    Collection is enough to prove it, and costs ~2s instead of a fourth full family run:
    `migrated_family_run` already exited 0 over all seven families, so every collected
    test in them PASSED. What remains to prove is that the fault tests are still THERE —
    that the count above is not 1 because someone deleted the tests that used to rebuild.
    """
    root = _repo_root()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *_family_dirs(root),
         "-k", FAULT_SELECTOR, "-q", "-p", "no:cacheprovider", "--collect-only"],
        cwd=root, env=dict(os.environ), capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, f"fault-test collection failed:\n{result.stdout[-3000:]}"

    match = re.search(r"(\d+)\s*/\s*\d+\s+tests\s+collected|(\d+)\s+tests?\s+collected", result.stdout)
    assert match, f"could not read the collected count from:\n{result.stdout[-2000:]}"
    collected = int(match.group(1) or match.group(2))
    assert collected >= MIN_FAULT_TESTS, (
        f"only {collected} fault-injection tests are collected, expected >= "
        f"{MIN_FAULT_TESTS}; coverage was dropped, not sped up"
    )
