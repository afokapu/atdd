# URN: test:govern-lifecycle:ship-package-data-and-consumer-ci:C009-SMOKE-001-consumer-sweep-collects-with-zero-errors-off-the-installed-wheel
# Acceptance: acc:govern-lifecycle:C009-SMOKE-001-consumer-sweep-collects-with-zero-errors-off-the-installed-wheel
# WMBT: wmbt:govern-lifecycle:C009
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""C009-SMOKE-001 — the shipped validators COLLECT in a real consumer repo.

Real infra: a wheel built from the checkout, `pip install`ed into a freshly
created virtualenv, and exercised from a `git init`'d directory that has no
`src/atdd/`. Nothing from the checkout is on the import path — so a data file that
did not ship is genuinely absent, not shadowed.

Why collection is the right invariant: a missing data file surfaces as an
IMPORT-time failure. `bind_rule()` runs at module scope, so a rule node that did
not ship raises `RuleNotInRegistryError` while pytest is still collecting, and the
whole sweep aborts before running a single test. On the pre-fix wheel that is 15
collection errors in `tester` and 15 in `coder`. Zero is the invariant.

Collection — not a green sweep. A consumer's `atdd validate <phase>` still fails
some tests for an unrelated reason (#954: toolkit self-tests carry no `platform`
marker, so they run in consumer mode and assert on `src/atdd/` and
`docs/smoke-audit.md`, which no consumer has). That is a different mechanism with
a different fix, and it is explicitly out of scope for #1474. Gating on a green
sweep would mean shipping a job that is red on arrival.
"""
from __future__ import annotations

import functools
import json
import re
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from ._wheel_harness import _SESSION_TMP, built_wheel

pytestmark = [pytest.mark.coach]

_PHASES = ("planner", "tester", "coder", "coach")


@functools.lru_cache(maxsize=1)
def _consumer_env() -> tuple[Path, Path, Path]:
    """(venv python, installed atdd package dir, synthetic consumer repo).

    The venv is real and clean: the wheel and its declared dependencies, nothing
    else. The consumer repo is a `git init`'d directory holding no toolkit source.
    """
    root = Path(_SESSION_TMP.name)

    venv_dir = root / "consumer-venv"
    venv.create(venv_dir, with_pip=True, clear=False)
    python = venv_dir / "bin" / "python"
    if not python.exists():  # Windows layout
        python = venv_dir / "Scripts" / "python.exe"

    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", "pytest", str(built_wheel())],
        check=True, capture_output=True, text=True,
    )

    pkg_dir = Path(
        subprocess.run(
            [str(python), "-c",
             "import atdd, pathlib; print(pathlib.Path(atdd.__file__).resolve().parent)"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    )

    consumer = root / "consumer-repo"
    consumer.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=consumer, check=True)

    return python, pkg_dir, consumer


def _collect(phase: str) -> tuple[int, str]:
    """Collect the installed package's `<phase>/validators/` from the consumer repo."""
    python, pkg_dir, consumer = _consumer_env()
    result = subprocess.run(
        [str(python), "-m", "pytest", str(pkg_dir / phase / "validators"),
         "-q", "-p", "no:cacheprovider", "--collect-only", "-m", "not platform"],
        capture_output=True, text=True, cwd=consumer,
    )
    output = result.stdout + result.stderr
    errors = int((re.search(r"(\d+) error", output) or [0, 0])[1])
    return errors, output


@pytest.mark.smoke
def test_c009_smoke_001_no_source_tree_leaks_into_the_consumer_env():
    """Anti-vacuity control: the package under test really is the wheel."""
    _, pkg_dir, consumer = _consumer_env()

    assert not (consumer / "src" / "atdd").exists(), (
        "the synthetic consumer repo contains a toolkit source tree — the sweep "
        "would resolve data files from it and the test would pass vacuously"
    )
    assert "site-packages" in str(pkg_dir), (
        f"the atdd under test is not an installed package ({pkg_dir}); the wheel's "
        f"contents are not what is being exercised"
    )


@pytest.mark.smoke
@pytest.mark.parametrize("phase", _PHASES)
def test_c009_smoke_001_consumer_sweep_collects_with_zero_errors(phase: str):
    errors, output = _collect(phase)

    assert errors == 0, (
        f"`atdd validate {phase}` hits {errors} pytest COLLECTION error(s) in a "
        f"consumer repo off the installed wheel. A data file the shipped validators "
        f"read at import did not ship, so the sweep aborts before running a single "
        f"test — this is #1369.\n\n{output[-3000:]}"
    )


@pytest.mark.smoke
def test_c009_smoke_001_wheel_completeness_gate_passes_against_the_installed_package():
    """The gate itself, run the only way it has ever been able to run."""
    python, pkg_dir, _ = _consumer_env()
    repo = Path(__file__).resolve().parents[4]

    result = subprocess.run(
        [str(python), "-m", "pytest",
         str(pkg_dir / "coach" / "validators" / "test_wheel_completeness.py"),
         "-q", "-p", "no:cacheprovider", "-rs"],
        capture_output=True, text=True, cwd=repo,  # cwd = the toolkit checkout
    )
    output = result.stdout + result.stderr

    assert result.returncode == 0, (
        f"the wheel-completeness gate FAILS against the installed wheel — a file the "
        f"source tree ships as package data is absent from the package:\n{output[-3000:]}"
    )
    assert " skipped" not in output or " passed" in output, (
        f"the gate did not execute a single assertion against a real wheel — it "
        f"skipped, which is the #451 defect this issue repairs:\n{output[-2000:]}"
    )
