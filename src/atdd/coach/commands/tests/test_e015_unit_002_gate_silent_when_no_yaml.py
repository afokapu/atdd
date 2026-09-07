# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E015-UNIT-002-gate-silent-when-no-yaml
# Acceptance: acc:govern-lifecycle:E015-UNIT-002-gate-silent-when-no-yaml
# WMBT: wmbt:govern-lifecycle:E015
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""acc:govern-lifecycle:E015-UNIT-002 — ATDDGate.verify() does not error and omits 'Agent Behavioral Rules' when .atdd/agent-rules.yaml absent."""
from __future__ import annotations

import sys
from io import StringIO
from unittest.mock import patch


def test_gate_silent_when_no_yaml(tmp_path):
    from atdd.coach.commands.gate import ATDDGate

    # No .atdd/agent-rules.yaml in tmp_path
    gate = ATDDGate(target_dir=tmp_path)

    # #1811: no projected agent file to stand in for any more.
    captured = StringIO()
    with patch("sys.stdout", captured):
        result = gate.verify()

    output = captured.getvalue()
    assert result == 0, f"expected return 0 when agent-rules.yaml absent, got {result}"
    assert "Agent Behavioral Rules" not in output, (
        f"must not print 'Agent Behavioral Rules' when file absent: {output!r}"
    )
