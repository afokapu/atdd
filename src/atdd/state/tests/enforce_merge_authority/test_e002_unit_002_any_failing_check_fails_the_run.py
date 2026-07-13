# URN: test:enforce-merge-authority:run-merge-checks:E002-UNIT-002-any-failing-check-fails-the-run
# Acceptance: acc:enforce-merge-authority:E002-UNIT-002-any-failing-check-fails-the-run
# WMBT: wmbt:enforce-merge-authority:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: with every required check passing the merge-authority run succeeds and exits zero; forcing any single check to fail fails the whole run and exits non-zero, naming the check that failed; and no required check is marked continue-on-error or advisory. Refs #1400.
"""One failing check fails the run — every time (E002-UNIT-002).

wagon: enforce-merge-authority | feature: run-merge-checks | phase: RED
WMBT: wmbt:enforce-merge-authority:E002

The whole authority model reduces to one behaviour: *any* failing check fails the run. A
run that reported six passes and shrugged at the seventh would be the advisory signal I6
exists to forbid — and the check it shrugged at would be, by construction, the one that
mattered.

So the run is evaluated with each check forced to fail in turn, one at a time. That is
also why the check set is data and each check is a function: a harness can substitute one,
which is exactly what makes the property testable rather than merely asserted. Refs #1400.
"""
from __future__ import annotations

from atdd.state import merge_authority, policy
from atdd.state.merge_authority import (
    REQUIRED_CHECKS,
    CheckResult,
    Context,
    run,
)

from ._helpers import repo_root


def _passing(name: str):
    return lambda context: CheckResult(name, True, f"{name}: forced pass")


def _failing(name: str):
    return lambda context: CheckResult(name, False, f"{name}: forced failure")


def test_e002_unit_002_any_failing_check_fails_the_run(tmp_path) -> None:
    """All-passing succeeds; each single forced failure fails the run and is named."""
    context = Context(repo=tmp_path, projection_dir=tmp_path, base_ref=None, head_ref="HEAD")

    # With every check passing, the run succeeds and exits zero.
    green = run(context, checks={name: _passing(name) for name in REQUIRED_CHECKS})
    assert green.ok
    assert green.exit_code == 0
    assert green.failed == []
    assert [result.name for result in green.results] == list(REQUIRED_CHECKS)
    assert "PASSED" in green.render()

    # Forcing ANY single check to fail fails the run — one at a time, all seven.
    for victim in REQUIRED_CHECKS:
        checks = {name: _passing(name) for name in REQUIRED_CHECKS}
        checks[victim] = _failing(victim)

        result = run(context, checks=checks)

        assert not result.ok, f"a failing {victim} must fail the whole run"
        assert result.exit_code == 1
        assert result.failed == [victim]
        # The run names the check that failed: a red run with no name is unactionable.
        assert victim in result.render()
        assert "FAILED" in result.render()
        # And every other check still ran — the run does not short-circuit and leave six
        # checks unreported, because the next thing the author does is fix them all.
        assert len(result.results) == len(REQUIRED_CHECKS)
        assert result.result_for(victim).ok is False
        assert all(r.ok for r in result.results if r.name != victim)

    # No required check is marked continue-on-error or advisory in the shipped workflow.
    workflow = policy.load_workflow(repo_root())
    assert policy.advisory_jobs(workflow) == []
    for job in workflow["jobs"].values():
        assert not job.get("continue-on-error")

    # An unknown check is a programming error, not a silently-skipped gate.
    try:
        run(context, only=["not-a-check"])
    except merge_authority.MergeAuthorityError as exc:
        assert "not-a-check" in str(exc)
    else:  # pragma: no cover - the raise above is the contract
        raise AssertionError("an unknown check must be refused, never skipped")
