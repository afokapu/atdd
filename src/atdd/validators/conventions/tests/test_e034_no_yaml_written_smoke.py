# URN: test:validate-conventions:tune-convention-suite:E034-SMOKE-001-no-yaml-written-in-real-checkout
# Acceptance: acc:validate-conventions:E034-SMOKE-001-no-yaml-written-in-real-checkout
# WMBT: wmbt:validate-conventions:E034
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E034 SMOKE — the migrated evaluator families leave no YAML residue (#1416).

Exercises a real checkout through real ``python -m pytest`` over the five migrated
evaluator fault families and asserts the three observable outcomes of E034-SMOKE-001:

  * the suite exits 0 (every migrated fault + baseline test passes),
  * ``git status`` reports no NEW residual modification to any tracked convention OR plan
    YAML — the injections write nothing at all now,
  * the fault is still CAUGHT: the migrated ``*fault*`` / ``*inject*`` tests are collected
    and green, so coverage was preserved, not removed to buy the speed.

Build counts and runtime are reported as measured numbers on the PR, never asserted —
CI wall-clock swings too much to gate on, and a timing budget is cheapest to satisfy by
deleting the very fault coverage this suite exists to protect.

Both tests here were themselves ``convention_filesystem_mutation`` until #1418, not because
they write anything — they only read ``git status`` — but because the nested pytest they
spawn used to run the loader fault tests, which DID write the tree. #1418 staged that last
group onto temp roots, so the child now writes nothing and these two CASCADE into the
parallel class. That is not an assertion made here; it is the runtime guard
(``_support/mutation_guard``) that decides, by fingerprinting the tree across the spawn. If
a writer ever returns to those family directories, the guard fails these two by name.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Convention YAML AND plan YAML — the two working-tree surfaces the migrated families
# used to rewrite. Both must be residue-free after the suite.
DIRTY_GLOBS = ["src/atdd/**/*.convention.yaml", "plan/**/*.yaml"]
MIGRATED_FAMILIES = ["coherence", "presence", "resolution", "coverage", "acyclicity"]
FAULT_SELECTOR = "fault or inject or catches_injected"
MIN_FAULT_TESTS = 8


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


def _family_dirs(root: Path) -> list[str]:
    base = root / "src" / "atdd" / "validators" / "conventions"
    return [str(base / fam) for fam in MIGRATED_FAMILIES]


def _dirty_yaml(root: Path) -> str:
    """`git status --porcelain` restricted to convention + plan YAML — the surface a
    filesystem fault would disturb."""
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", *DIRTY_GLOBS],
        cwd=root, capture_output=True, text=True, timeout=120,
    )
    return result.stdout


def test_migrated_families_leave_no_yaml_residue() -> None:
    root = _repo_root()

    before = _dirty_yaml(root)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", *_family_dirs(root),
         "-q", "-p", "no:cacheprovider"],
        cwd=root, env=dict(os.environ), capture_output=True, text=True, timeout=900,
    )

    after = _dirty_yaml(root)

    assert result.returncode == 0, f"a migrated family is red:\n{result.stdout[-3000:]}"
    assert after == before, (
        "the migrated evaluator families left a tracked convention or plan YAML modified — "
        f"in-memory injection is supposed to write nothing and loaders must revert. "
        f"git status delta:\n{after}"
    )


def test_migrated_faults_are_still_caught() -> None:
    """Coverage preserved: the migrated fault-injection tests are still collected AND green."""
    root = _repo_root()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *_family_dirs(root),
         "-k", FAULT_SELECTOR, "-q", "-p", "no:cacheprovider"],
        cwd=root, env=dict(os.environ), capture_output=True, text=True, timeout=900,
    )
    assert result.returncode == 0, f"migrated fault tests are red:\n{result.stdout[-3000:]}"

    match = re.search(r"(\d+)\s+passed", result.stdout)
    assert match, f"could not read the passed count from:\n{result.stdout[-2000:]}"
    passed = int(match.group(1))
    assert passed >= MIN_FAULT_TESTS, (
        f"only {passed} fault-injection tests ran, expected >= {MIN_FAULT_TESTS}; "
        "coverage was dropped, not sped up"
    )
