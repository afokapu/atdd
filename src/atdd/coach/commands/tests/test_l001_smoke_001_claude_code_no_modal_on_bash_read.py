# URN: test:spawn-agents:spawn-time-non-interactive-convention:L001-SMOKE-001-claude-code-no-modal-on-bash-read
# Acceptance: acc:spawn-agents:L001-SMOKE-001-claude-code-no-modal-on-bash-read
# WMBT: wmbt:spawn-agents:L001
# Phase: SMOKE
# Layer: smoke
# Runtime: python
# Assertion: behavioral
"""L001-SMOKE-001 — claude-code adapter's non_interactive_smoke spawns claude
with the declared permission_flags + allowed_tools and confirms no modal marker
appears in the captured output.

SMOKE: requires a real `claude` CLI installed on PATH. The test skips
gracefully when the CLI is absent so CI passes without a Claude installation.
"""
from __future__ import annotations

import shutil

import pytest


@pytest.mark.smoke
def test_claude_code_non_interactive_smoke_no_modal():
    """L001-SMOKE-001: call non_interactive_smoke() and assert no modal fires."""
    if not shutil.which("claude"):
        pytest.skip("claude CLI not on PATH — smoke test requires a real installation")

    from atdd.coach.commands.spawn import ADAPTER_REGISTRY

    adapter = ADAPTER_REGISTRY["claude-code"]
    assert adapter.non_interactive_smoke is not None, (
        "L001: claude-code adapter must have a non_interactive_smoke callable"
    )

    # Raises RuntimeError if a modal-class string appears in the output.
    adapter.non_interactive_smoke()
