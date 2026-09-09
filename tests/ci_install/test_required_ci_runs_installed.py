# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""#1604 — required CI runs the repository's tests against an INSTALLED package.

Its sibling, :mod:`test_smoke_attestation_hook_requires_install`, establishes the
mechanism and proves it causally: an entry-point hook is inert until the package
is installed, and one job — ``attestation-hook-install`` — demonstrates that on a
real venv. This module asserts the consequence the issue's title actually
promised, over the WHOLE workflow: *every* step that runs pytest over this
checkout installs the distribution first, and none of them re-introduces
``PYTHONPATH=src``.

Why the sibling was not enough. It reads one job. When #1604 first shipped, the
other twelve pytest steps still ran uninstalled, so the substrate plugin — and
the #1602 smoke-execution attestation that attaches to it — loaded in exactly the
one job that ran none of the repository's smoke tests. #1664's census measured
the result and named it in one number: ``ci-can-record: 0``. Every acceptance
whose anchored test is a real smoke test sat on a path CI either never ran or ran
without the distribution, so no acceptance here could be attested by CI at all,
and declaring ``execution_kind: live_smoke`` on any of them would have made
``SMOKE->REFACTOR`` reachable only through ``--force`` — the rubber stamp E069
names and #1602's opt-in design exists to prevent.

WHAT IS ASSERTED, and what deliberately is not. Not "these particular jobs";
a per-job allowlist rots the moment a job is added, and the job that would be
forgotten is the new one. The predicate is over the invocation: a step that
hands pytest a path inside this checkout runs it installed. A job that runs
pytest against an *installed wheel elsewhere* — ``validate-consumer``, which
points pytest at the venv's site-packages — is not one of those steps and is not
policed here; it has its own oracle.

The reader is :func:`atdd.tester.substrate.ci_runner.ci_pytest_steps`, the
same one #1664's census classifies with. That is deliberate: if this guard had
its own reader, the guard and the census could disagree about what CI runs, and
the census is how anyone would check whether the fix held.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pytest

from atdd.tester.substrate.ci_runner import CiPytestStep, ci_pytest_steps

#: ``tests/ci_install/<this file>`` — resolved from the file, not the cwd.
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"


def workflow_texts() -> Dict[str, str]:
    """Every workflow in this repository, by file name."""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(WORKFLOW_DIR.glob("*.yml"))
    }


@pytest.fixture(scope="module")
def pytest_steps() -> List[CiPytestStep]:
    """Every CI step that runs pytest over a path inside this checkout."""
    steps = ci_pytest_steps(workflow_texts())
    if not steps:
        pytest.fail(
            f"no workflow under {WORKFLOW_DIR} runs pytest over this checkout. Either CI "
            f"stopped running the repository's tests, or the reader stopped seeing them — "
            f"and an empty population would make every assertion below pass vacuously"
        )
    return steps


def test_every_ci_pytest_step_runs_against_an_installed_distribution(
    pytest_steps: List[CiPytestStep],
) -> None:
    """The #1604 invariant. Uninstalled means the hook is inert in that job."""
    uninstalled = [s for s in pytest_steps if not s.installs_dist]
    assert not uninstalled, (
        "these CI steps run this repository's tests without installing the package, so "
        "pytest discovers no `pytest11` entry point, the substrate plugin never loads, "
        "and any live-smoke test they run records nothing while reporting `passed`:\n"
        + "\n".join(
            f"  {s.workflow}::{s.job} — {s.step or '(unnamed step)'} -> {', '.join(s.targets)}"
            for s in uninstalled
        )
        + "\nAdd `pip3 install -e .` to the job before its pytest step."
    )


def test_no_ci_pytest_step_reintroduces_pythonpath(
    pytest_steps: List[CiPytestStep],
) -> None:
    """`PYTHONPATH=src` alongside the install is the defect's shape, not its cure.

    Asserted separately from the install because it fails differently and more
    quietly. A step carrying BOTH still loads the hook — the metadata is there —
    so it stays green while re-teaching the spelling that made the whole
    repository's CI inert, and the next job copied from it will carry the
    PYTHONPATH and not the install. ``pyproject.toml`` already sets
    ``pythonpath = ["src"]`` for pytest, so the variable buys nothing even as a
    convenience.
    """
    with_pythonpath = [s for s in pytest_steps if s.sets_pythonpath]
    assert not with_pythonpath, (
        "these CI pytest steps set PYTHONPATH:\n"
        + "\n".join(
            f"  {s.workflow}::{s.job} — {s.step or '(unnamed step)'}"
            for s in with_pythonpath
        )
        + "\nThe package is installed; pytest's ini `pythonpath = [\"src\"]` covers the "
        "rest. Setting it here only restores the invocation #1604 exists to remove."
    )


def test_the_reader_still_sees_the_multi_target_job(
    pytest_steps: List[CiPytestStep],
) -> None:
    """A step passing many paths must be read as many, not as its first one.

    Not a test of the workflow but of the reading of it, and it is here because
    getting this wrong is silent in both directions. `regression-suite-test`
    hands pytest 19 paths across a line-continued block; a reader that stopped at
    `pytest \\` saw a job running nothing, and one that took only the first
    argument saw it running a twentieth of what it runs. Either way the census
    reports those paths as `not-run-by-ci` — a claim that CI has no opinion about
    the biggest suite it executes.
    """
    widest = max(pytest_steps, key=lambda s: len(s.targets))
    assert len(widest.targets) > 1, (
        f"no CI step is read as running more than one path; the widest is "
        f"{widest.job} with {widest.targets}. A pytest invocation takes many paths, so "
        f"this means the reader is taking the first argument and dropping the rest"
    )
    for step in pytest_steps:
        for target in step.targets:
            assert (REPO_ROOT / target).exists(), (
                f"{step.workflow}::{step.job} runs pytest against {target!r}, which does "
                f"not exist in this checkout — CI is either testing nothing there or the "
                f"reader has mis-parsed the command"
            )
