# URN: test:spawn-agents:spawn-time-non-interactive-convention:D002-SMOKE-001-session-convention-committed-and-loadable
# Acceptance: acc:spawn-agents:D002-SMOKE-001-session-convention-committed-and-loadable
# WMBT: wmbt:spawn-agents:D002
# Phase: SMOKE
# Layer: smoke
# Runtime: python
# Assertion: behavioral
"""D002-SMOKE-001 — session.convention.yaml is committed on disk, parseable
as YAML, and contains spawn_time with all required subsections.

SMOKE: reads the real file from the deployed codebase.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.smoke
def test_session_convention_committed_and_loadable():
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML not installed")

    convention_path = (
        Path(__file__).parent.parent.parent
        / "conventions"
        / "session.convention.yaml"
    )
    assert convention_path.exists(), (
        f"D002-SMOKE-001: session.convention.yaml not found at {convention_path}. "
        "D002 convention file not committed."
    )
    data = yaml.safe_load(convention_path.read_text(encoding="utf-8"))
    assert "spawn_time" in data, (
        "D002-SMOKE-001: session.convention.yaml missing 'spawn_time' key."
    )
    spawn_time = data["spawn_time"]
    required_keys = {"freedom_layer", "leash_layer", "deny_pattern_escalation", "slash_command_prohibition"}
    missing = required_keys - set(spawn_time.keys())
    assert not missing, (
        f"D002-SMOKE-001: spawn_time section missing keys: {missing}"
    )
    convention_text = convention_path.read_text(encoding="utf-8")
    assert "atdd agent escalate" in convention_text, (
        "D002-SMOKE-001: 'atdd agent escalate' not found in session.convention.yaml. "
        "deny_pattern_escalation command must be documented."
    )
