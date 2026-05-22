# URN: test:spawn-agents:spawn-time-non-interactive-convention:D002-UNIT-001-session-convention-has-spawn-time-section
# URN: test:spawn-agents:spawn-time-non-interactive-convention:D002-UNIT-002-session-convention-references-deny-pattern-escalation
# Acceptance: acc:spawn-agents:D002-UNIT-001-session-convention-has-spawn-time-section
# Acceptance: acc:spawn-agents:D002-UNIT-002-session-convention-references-deny-pattern-escalation
"""D002 — session.convention.yaml has spawn_time section with freedom-with-a-leash policy.

RED: session.convention.yaml may not exist or may lack a spawn_time section.
GREEN: file exists with spawn_time.freedom_layer + spawn_time.leash_layer.
"""
from pathlib import Path
import pytest
import yaml


SESSION_CONVENTION = Path("src/atdd/coach/conventions/session.convention.yaml")


def test_session_convention_file_exists():
    assert SESSION_CONVENTION.is_file(), (
        f"{SESSION_CONVENTION} does not exist. "
        "D002: create src/atdd/coach/conventions/session.convention.yaml with spawn_time section."
    )


def test_session_convention_has_spawn_time_key():
    data = yaml.safe_load(SESSION_CONVENTION.read_text())
    assert "spawn_time" in data, (
        f"session.convention.yaml missing 'spawn_time' top-level key. "
        "D002: add spawn_time section documenting the freedom-with-a-leash policy."
    )


def test_spawn_time_has_freedom_layer():
    data = yaml.safe_load(SESSION_CONVENTION.read_text())
    spawn_time = data.get("spawn_time", {})
    assert "freedom_layer" in spawn_time, (
        "session.convention.yaml spawn_time missing 'freedom_layer'. "
        "D002: document the pre-granted allowlist layer."
    )


def test_spawn_time_has_leash_layer():
    data = yaml.safe_load(SESSION_CONVENTION.read_text())
    spawn_time = data.get("spawn_time", {})
    assert "leash_layer" in spawn_time, (
        "session.convention.yaml spawn_time missing 'leash_layer'. "
        "D002: document the cli-return observer correction layer (issue #824)."
    )


def test_spawn_time_references_atdd_agent_escalate():
    text = SESSION_CONVENTION.read_text()
    assert "atdd agent escalate" in text, (
        "session.convention.yaml does not reference 'atdd agent escalate'. "
        "D002: the spawn_time section must document the deny-pattern escalation path."
    )
