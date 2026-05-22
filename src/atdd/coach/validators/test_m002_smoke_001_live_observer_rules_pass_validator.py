# URN: test:spawn-agents:spawn-time-non-interactive-convention:M002-SMOKE-001-live-observer-rules-pass-layer-b-validator
# Acceptance: acc:spawn-agents:M002-SMOKE-001-live-observer-rules-pass-layer-b-validator
# WMBT: wmbt:spawn-agents:M002
# Phase: SMOKE
# Layer: smoke
# Runtime: python
# Assertion: behavioral
"""M002-SMOKE-001 — the deployed observer_rules/ directory passes
check_observer_rules_no_slash_send with zero violations.

SMOKE: scans the real observer_rules directory, not synthetic fixtures.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.smoke
def test_live_observer_rules_pass_layer_b_validator():
    from atdd.coach.validators.test_spawn_non_interactive_validator import (
        check_observer_rules_no_slash_send,
    )

    observer_rules_dir = Path(__file__).parent.parent / "observer_rules"
    if not observer_rules_dir.is_dir():
        pytest.skip(f"observer_rules dir not found at {observer_rules_dir}")

    rule_files = [
        f for f in observer_rules_dir.glob("*.py")
        if not f.name.startswith("__")
    ]
    if not rule_files:
        pytest.skip("No observer rule files found")

    violations = check_observer_rules_no_slash_send(rule_files)
    assert not violations, (
        "M002-SMOKE-001: live observer rules contain slash-command injection:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
