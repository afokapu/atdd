# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E015-UNIT-001-gate-includes-portable-rules-when-yaml-exists
# Acceptance: acc:govern-lifecycle:E015-UNIT-001-gate-includes-portable-rules-when-yaml-exists
# WMBT: wmbt:govern-lifecycle:E015
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""acc:govern-lifecycle:E015-UNIT-001 — ATDDGate.verify() prints 'Agent Behavioral Rules' when .atdd/agent-rules.yaml exists."""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import yaml


def test_gate_includes_portable_rules_when_yaml_exists(tmp_path):
    from atdd.coach.commands.gate import ATDDGate

    # Create .atdd/agent-rules.yaml in tmp_path
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()
    rules_file = atdd_dir / "agent-rules.yaml"
    rules_file.write_text(yaml.dump({
        "rules": [
            {"id": "AR-001", "rule": "Never pass --dangerously-skip-permissions to claude CLI"},
            {"id": "AR-002", "rule": "Search for duplicates before filing a new issue"},
        ]
    }))

    gate = ATDDGate(target_dir=tmp_path)

    # Patch _get_synced_files to avoid needing real agent config files
    fake_files = {"claude": {"file": "CLAUDE.md", "exists": True, "has_block": True, "hash": "abc123"}}
    captured = StringIO()
    with patch.object(gate, "_get_synced_files", return_value=fake_files):
        with patch("sys.stdout", captured):
            result = gate.verify()

    output = captured.getvalue()
    assert "Agent Behavioral Rules" in output, f"expected 'Agent Behavioral Rules' header in gate output: {output!r}"
    assert "dangerously-skip-permissions" in output or "AR-001" in output, (
        f"expected rule content in gate output: {output!r}"
    )
