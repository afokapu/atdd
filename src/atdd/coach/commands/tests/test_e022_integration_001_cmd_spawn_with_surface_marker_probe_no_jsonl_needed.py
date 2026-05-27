# URN: test:spawn-agents:E022-INTEGRATION-001-cmd-spawn-with-surface-marker-probe-no-jsonl-needed
# Acceptance: acc:spawn-agents:E022-INTEGRATION-001-cmd-spawn-with-surface-marker-probe-no-jsonl-needed
# WMBT: wmbt:spawn-agents:E022
# Phase: GREEN
# Layer: backend.integration
# Runtime: python
# Assertion: behavioral
"""E022-INTEGRATION-001 — Full cmd_spawn with FakeMultiplexer returning '❯' succeeds with no JSONL at probe time

RED: fails until cmd_spawn readiness_probe dispatch is implemented — pending E022 GREEN phase.
"""
from __future__ import annotations

import pytest


def test_cmd_spawn_with_surface_marker_probe_no_jsonl_needed():
    pytest.fail(
        "RED: Full cmd_spawn with FakeMultiplexer returning '❯' succeeds with no JSONL at probe time — pending E022 GREEN phase"
    )
