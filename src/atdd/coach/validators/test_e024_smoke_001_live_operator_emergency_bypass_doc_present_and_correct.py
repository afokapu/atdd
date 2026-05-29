# URN: test:spawn-agents:claude-md-slim-and-debanner:E024-SMOKE-001-live-operator-emergency-bypass-doc-present-and-correct
# Acceptance: acc:spawn-agents:E024-SMOKE-001-live-operator-emergency-bypass-doc-present-and-correct
# WMBT: wmbt:spawn-agents:E024
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""E024-SMOKE-001 — live docs/operator-emergency-bypass.md exists and is correct post-merge.

SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure.

After PR #867 merges, confirms against the live filesystem that the operator doc
exists and documents the 'atdd emergency' CLI path.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
_DOC_PATH = REPO_ROOT / "docs" / "operator-emergency-bypass.md"
_REQUIRED_CLI_STRING = "atdd emergency"


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_live_operator_emergency_bypass_doc_present_and_correct():
    """E024-SMOKE-001: docs/operator-emergency-bypass.md exists and contains 'atdd emergency'."""
    assert _DOC_PATH.exists(), (
        f"docs/operator-emergency-bypass.md not found at {_DOC_PATH}.\n"
        "E024 SMOKE requires this file to be present in the live repo after merge."
    )

    text = _DOC_PATH.read_text(encoding="utf-8")

    assert _REQUIRED_CLI_STRING in text, (
        f"Live docs/operator-emergency-bypass.md does not contain '{_REQUIRED_CLI_STRING}'.\n"
        "E024 SMOKE requires the operator doc to document the CLI emergency path."
    )
