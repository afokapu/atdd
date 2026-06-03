# URN: test:mediate-worker-decisions:bridge-cmux-feed:C003-UNIT-001-dangerous-tool-input-human-required
# Acceptance: acc:mediate-worker-decisions:C003-UNIT-001-dangerous-tool-input-human-required
# WMBT: wmbt:mediate-worker-decisions:C003
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""C003-UNIT-001 — a dangerous tool_input classifies human_required.

A permission whose tool_input is a dangerous command classifies human_required;
a safe command classifies auto.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.tool_input_safety import (
    classify,
)


def test_dangerous_command_is_human_required():
    assert classify("git push origin main") == "human_required"


def test_safe_command_is_auto():
    assert classify("ls -la") == "auto"
