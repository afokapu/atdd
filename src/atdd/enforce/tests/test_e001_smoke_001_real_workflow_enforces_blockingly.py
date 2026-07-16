# URN: test:enforce-conventions-ci:E001-SMOKE-001-real-workflow-enforces-blockingly
# Acceptance: acc:enforce-conventions-ci:E001-SMOKE-001-real-workflow-enforces-blockingly
# WMBT: wmbt:enforce-conventions-ci:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:enforce-conventions-ci:E001-SMOKE-001-real-workflow-enforces-blockingly.

Over the repository's REAL committed ``.github/workflows/atdd-validate.yml`` — the
live wiring that decides whether a convention regression can reach main:

  * the `atdd enforce` VERDICT step carries neither ``continue-on-error: true`` nor
    ``|| true`` — a strict FAIL exits the job non-zero (#1359 shipped it ADVISORY;
    this is the flip that is the point of train 0007);
  * it runs under the ratchet baseline, so the pre-existing debt is held flat rather
    than reding the first blocking build (the flip and the baseline are ONE change);
  * the job is a member of the ``validate-gate`` ``needs`` fan-in AND the gate fails
    on its non-success result — so the blocking step actually blocks the MERGE.

This is a guard against the flip being quietly reverted: re-adding either swallow
guard, or dropping the job from the fan-in, reds this test.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.ci_gate import (
    ENFORCE_JOB,
    enforce_job_is_required,
    path_b_is_blocking,
    verdict_uses_ratchet,
)
from atdd.enforce.ratchet import RATCHET_PATH


def test_real_enforce_verdict_step_is_blocking() -> None:
    repo = find_repo_root()

    assert path_b_is_blocking(repo) is True, (
        "the real `atdd enforce` verdict step is NOT blocking — it still carries "
        "`continue-on-error: true` or `|| true`, so a strict convention FAIL would "
        "report SUCCESS and reach main. This is exactly the #1359 advisory stage "
        "that #1428 exists to end."
    )


def test_real_verdict_step_runs_under_the_ratchet_baseline() -> None:
    repo = find_repo_root()

    assert verdict_uses_ratchet(repo) is True, (
        "the real verdict step is blocking but does NOT pass --ratchet — it will red "
        "the build on the repository's pre-existing debt and be reverted within the hour"
    )
    # ...and the baseline it names is actually committed.
    assert (repo / RATCHET_PATH).is_file(), f"the committed baseline {RATCHET_PATH} is missing"


def test_real_enforce_job_is_required_by_the_validate_gate() -> None:
    repo = find_repo_root()

    assert enforce_job_is_required(repo) is True, (
        f"the real validate-gate does not require {ENFORCE_JOB!r} (it must both list "
        f"it in `needs` AND check its result — under `if: always()` a needs entry "
        f"alone is decorative). A blocking step in a job nobody demands blocks nothing."
    )
