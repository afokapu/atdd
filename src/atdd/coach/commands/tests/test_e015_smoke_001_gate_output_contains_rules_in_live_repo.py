# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E015-SMOKE-001-gate-output-contains-rules-in-live-repo
# Acceptance: acc:govern-lifecycle:E015-SMOKE-001-gate-output-contains-rules-in-live-repo
# WMBT: wmbt:govern-lifecycle:E015
# Phase: SMOKE
# Layer: backend.integration
# Assertion: behavioral

"""acc:govern-lifecycle:E015-SMOKE-001 — atdd gate on this repo outputs 'Agent Behavioral Rules'."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_gate_output_contains_rules_in_live_repo():
    rules_path = Path(".atdd/agent-rules.yaml")
    if not rules_path.exists():
        pytest.skip(".atdd/agent-rules.yaml not yet committed — skipping smoke test")

    result = subprocess.run(
        [sys.executable, "-m", "atdd.coach.cli", "gate"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"atdd gate exited non-zero: {result.stderr}"
    assert "Agent Behavioral Rules" in result.stdout, (
        f"'Agent Behavioral Rules' section missing from gate output: {result.stdout!r}"
    )
