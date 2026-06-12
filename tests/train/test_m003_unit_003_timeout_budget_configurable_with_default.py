# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:M003-UNIT-003-timeout-budget-configurable-with-default
# Acceptance: acc:spawn-agents:M003-UNIT-003-timeout-budget-configurable-with-default
# WMBT: wmbt:spawn-agents:M003
# Phase: GREEN
# Layer: backend.application
# Assertion: behavioral
"""M003-UNIT-003 — the warm-resume timeout budget is configurable, defaults to a
sane positive value when unset, and rejects non-positive values.

RED: fails until ``resolve_warm_resume_budget`` exists in
``atdd.train.warm_resume_watchdog``.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.coder]


def test_custom_value_is_honored():
    from atdd.train.warm_resume_watchdog import resolve_warm_resume_budget

    assert resolve_warm_resume_budget(42.0) == 42.0


def test_unset_value_uses_a_sane_positive_default():
    from atdd.train.warm_resume_watchdog import resolve_warm_resume_budget

    default = resolve_warm_resume_budget(None)
    assert default > 0, "an unset budget must default to a positive value (never disabled)"


def test_non_positive_value_is_rejected():
    from atdd.train.warm_resume_watchdog import resolve_warm_resume_budget

    with pytest.raises((ValueError, TypeError)):
        resolve_warm_resume_budget(0)
    with pytest.raises((ValueError, TypeError)):
        resolve_warm_resume_budget(-5)
