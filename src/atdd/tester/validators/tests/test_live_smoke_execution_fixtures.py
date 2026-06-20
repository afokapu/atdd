# URN: test:govern-lifecycle:live-smoke-execution-enforcement:E055-INTEGRATION-001-evaluator-fires-on-self-skipping-live-smoke-test
# Acceptance: acc:govern-lifecycle:E055-UNIT-001-convention-declares-live-smoke-execution-rule
# Acceptance: acc:govern-lifecycle:E055-INTEGRATION-001-evaluator-fires-on-self-skipping-live-smoke-test
# Acceptance: acc:govern-lifecycle:E055-INTEGRATION-002-detect-self-skip-classifies-mechanisms
# WMBT: wmbt:govern-lifecycle:E055
# Phase: GREEN
# Layer: application
# Runtime: python

"""Coverage for the live-smoke execution-enforcement substrate rule (issue #1151).

Proves ``wmbt:govern-lifecycle:E055``:

  - ``acceptance-violation.convention.yaml`` declares
    ``tester.acceptance-violation.live-smoke-acceptance-must-execute`` (strict,
    severity 4), ``bind_rule()`` resolves it, and its recipe pointer names a
    recipe file that exists (UNIT-001).
  - ``evaluate_live_smoke_execution`` emits exactly one ``Violation`` for a
    ``execution_kind: live_smoke`` acceptance anchored to a self-skipping test
    and stays silent for one anchored to a non-skipping test (INTEGRATION-001).
  - ``detect_self_skip`` classifies each self-skip mechanism and returns None
    for a clean source (INTEGRATION-002).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.rule_binding import bind_rule
from atdd.tester.validators.test_live_smoke_execution import (
    detect_self_skip,
    evaluate_live_smoke_execution,
)


pytestmark = [pytest.mark.platform]


_RULE_ID = "tester.acceptance-violation.live-smoke-acceptance-must-execute"

_SELF_SKIPPING_TEST = '''
# Acceptance: acc:demo:X-SMOKE-001
import pytest
from ..live_smoke import live_smoke_available
def test_real_thing():
    reason = live_smoke_available()
    if reason:
        pytest.skip(reason)
    assert real_infra_behaviour() == "ok"
'''

_CLEAN_TEST = '''
# Acceptance: acc:demo:X-SMOKE-002
def test_real_thing():
    assert real_infra_behaviour() == "ok"
'''


def test_e055_unit_001_convention_declares_live_smoke_execution_rule() -> None:
    """AC-UNIT-001: the rule binds (strict, sev 4) and its recipe exists."""
    rule = bind_rule(_RULE_ID)
    assert rule.rule_id == _RULE_ID
    assert rule.severity == 4
    assert str(rule.disposition) == "strict" or getattr(rule, "disposition", None) == "strict"
    recipe = (
        Path(__file__).resolve().parents[2]
        / "conventions"
        / "live-smoke-execution.recipe.yaml"
    )
    assert recipe.is_file(), f"recipe missing: {recipe}"


def test_e055_integration_001_evaluator_fires_on_self_skipping_live_smoke_test() -> None:
    """AC-INTEGRATION-001: one Violation for the skipping test, none for the clean one."""
    violations = evaluate_live_smoke_execution(
        [
            (
                "plan/demo/X.yaml:acceptances[0]",
                "acc:demo:X-SMOKE-001",
                [("tests/test_x_smoke.py", _SELF_SKIPPING_TEST)],
            ),
            (
                "plan/demo/X.yaml:acceptances[1]",
                "acc:demo:X-SMOKE-002",
                [("tests/test_y_smoke.py", _CLEAN_TEST)],
            ),
        ]
    )
    assert len(violations) == 1
    v = violations[0]
    assert v.rule_id == _RULE_ID
    assert v.location == "tests/test_x_smoke.py"
    assert "acc:demo:X-SMOKE-001" in v.detail
    assert "self-skip" in v.detail


def test_e055_integration_002_detect_self_skip_classifies_mechanisms() -> None:
    """AC-INTEGRATION-002: each mechanism is recognized; clean source returns None."""
    assert detect_self_skip("def t():\n    pytest.skip('x')\n") is not None
    assert detect_self_skip("v = pytest.importorskip('cmux')\n") is not None
    assert detect_self_skip("@pytest.mark.skip\ndef t(): ...\n") == "@pytest.mark.skip"
    assert (
        detect_self_skip("@pytest.mark.skipif(not HAVE, reason='x')\ndef t(): ...\n")
        == "@pytest.mark.skipif"
    )
    assert detect_self_skip("r = live_smoke_available()\n") is not None
    assert detect_self_skip("def t():\n    assert real() == 'ok'\n") is None
