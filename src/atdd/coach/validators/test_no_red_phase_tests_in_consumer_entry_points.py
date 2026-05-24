"""
Regression validator: no Phase:RED test files may be reachable from
consumer-facing validator entry points without a @pytest.mark.platform guard.

This validator is the permanent prevention mechanism for the class of bug
documented in wmbt:govern-lifecycle:E025 (#846): ATDD ships its own
RED-phase tests in the release wheel and they leak into consumer
atdd validate planner runs, blocking every plan/ push.

The fix has two parts:
  1. TestRunner.run_tests() now injects 'not platform' before the
     split/no-split branch (E025 scope gate).
  2. This validator catches any future RED test that forgets the platform
     guard, so the class cannot recur silently.

Phase: GREEN (this file ships in the release wheel and runs in consumer mode,
but it is consumer-safe: it only inspects ATDD's own package paths, which
always exist in the installed wheel, and passes for well-guarded files).
"""
from __future__ import annotations

from pathlib import Path

import atdd
import pytest

from atdd.coach.validators.red_phase_leak_scanner import scan_for_red_phase_leaks


_ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
_VALIDATOR_PHASES = ["planner", "tester", "coder", "coach"]


@pytest.mark.platform
@pytest.mark.parametrize("phase", _VALIDATOR_PHASES)
def test_no_red_phase_leak_in_validator_phase(phase: str) -> None:
    """
    ACC: acc:govern-lifecycle:E025-UNIT-004/005 (regression guard)

    Every test file in {phase}/validators/ that declares 'Phase: RED' in
    its module docstring must have @pytest.mark.platform on every test
    function. Files without the guard would be collected in consumer
    atdd validate {phase} runs and fail on every push.
    """
    validator_dir = _ATDD_PKG_DIR / phase / "validators"
    if not validator_dir.is_dir():
        pytest.skip(f"validator dir not found: {validator_dir}")

    violations = scan_for_red_phase_leaks(validator_dir)

    assert not violations, (
        f"Phase:RED test files in {phase}/validators/ lack @pytest.mark.platform:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nFix: add @pytest.mark.platform to every test function in these files "
        "so they are excluded from consumer validator sweeps. See wmbt:govern-lifecycle:E025."
    )
