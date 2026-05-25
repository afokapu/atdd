# URN: test:govern-lifecycle:smoke-false-green-prevention:E028-INTEGRATION-001-no-false-positive-on-real-entry-point
# Acceptance: acc:govern-lifecycle:E028-INTEGRATION-001-no-false-positive-on-real-entry-point
# WMBT: wmbt:govern-lifecycle:E028
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""
GREEN: scan_for_synthetic_fixture_bypass must return an empty violation list
when the SMOKE test uses subprocess.run(['atdd', 'spawn', ...]) with no
FakeMultiplexer import.  Currently fails (stub) — becomes GREEN once
test_smoke_synthetic_fixture_bypass.py is implemented.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.planner]


def test_no_false_positive_on_real_entry_point(tmp_path):
    """Validator emits no violations for a SMOKE test that drives atdd spawn."""
    pytest.fail(
        "GREEN stub — implement after test_smoke_synthetic_fixture_bypass.py is created. "
        "The validator must return [] when the test file uses subprocess.run(['atdd', 'spawn', ...])"
        " with no FakeMultiplexer or cat/sleep/python stubs."
    )
