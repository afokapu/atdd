# URN: test:validate-conventions:tune-convention-suite:E033-SMOKE-001-no-yaml-written-in-real-checkout
# Acceptance: acc:validate-conventions:E033-SMOKE-001-no-yaml-written-in-real-checkout
# WMBT: wmbt:validate-conventions:E033
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E033 SMOKE — the binding family writes no convention YAML in a real checkout (#1415).

Exercises a real checkout through real ``python -m pytest`` over the binding family and
asserts the three observable outcomes of E033-SMOKE-001:

  * the suite exits 0 (all binding fault + baseline tests pass),
  * ``git status`` reports no NEW modification to any tracked convention YAML — the
    in-memory injection never touches the working tree,
  * the fault is still CAUGHT: the four ``*_convention_fault`` tests are collected and
    green, so coverage was preserved, not removed to buy the speed.

Build counts and runtime are reported as measured numbers on the PR, never asserted —
CI wall-clock swings too much to gate on, and a timing budget is cheapest to satisfy by
deleting the very fault coverage this suite exists to protect.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

CONVENTION_GLOB = "src/atdd/**/*.convention.yaml"
FAULT_SELECTOR = "convention_fault"
MIN_FAULT_TESTS = 4


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


def _binding_dir(root: Path) -> Path:
    return root / "src" / "atdd" / "validators" / "conventions" / "binding"


def _dirty_conventions(root: Path) -> str:
    """`git status --porcelain` restricted to convention YAML — the modification surface."""
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", CONVENTION_GLOB],
        cwd=root, capture_output=True, text=True, timeout=120,
    )
    return result.stdout


def test_binding_family_writes_no_convention_yaml() -> None:
    root = _repo_root()

    before = _dirty_conventions(root)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(_binding_dir(root)),
         "-q", "-p", "no:cacheprovider"],
        cwd=root, env=dict(os.environ), capture_output=True, text=True, timeout=900,
    )

    after = _dirty_conventions(root)

    assert result.returncode == 0, f"binding family is red:\n{result.stdout[-3000:]}"
    assert after == before, (
        "the binding suite modified a tracked convention YAML — in-memory injection is "
        f"supposed to write nothing. git status delta:\n{after}"
    )


def test_binding_fault_is_still_caught() -> None:
    """Coverage preserved: the fault-injection tests are still collected AND green."""
    root = _repo_root()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(_binding_dir(root)),
         "-k", FAULT_SELECTOR, "-q", "-p", "no:cacheprovider"],
        cwd=root, env=dict(os.environ), capture_output=True, text=True, timeout=900,
    )
    assert result.returncode == 0, f"binding fault tests are red:\n{result.stdout[-3000:]}"

    match = re.search(r"(\d+)\s+passed", result.stdout)
    assert match, f"could not read the passed count from:\n{result.stdout[-2000:]}"
    passed = int(match.group(1))
    assert passed >= MIN_FAULT_TESTS, (
        f"only {passed} fault-injection tests ran, expected >= {MIN_FAULT_TESTS}; "
        "coverage was dropped, not sped up"
    )
