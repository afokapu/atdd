# URN: test:spawn-agents:E025-UNIT-002-graph-launch-prompt-output-under-2kb
# Acceptance: acc:spawn-agents:E025-UNIT-002-graph-launch-prompt-output-under-2kb
# WMBT: wmbt:spawn-agents:E025
# Phase: RED
# Layer: unit
"""E025-UNIT-002 — wagon-scoped launch-prompt output for spawn-agents is ≤ 2 KB.

Invokes build_wagon_launch_prompt("spawn-agents") against the real plan/
directory (the test runner's working directory must include the repo root)
and asserts the UTF-8 byte length is ≤ 2048.

Phase RED: fails with ImportError — build_wagon_launch_prompt does not yet
exist in atdd.coach.commands.issue_graph.
Phase GREEN: function exists; output for spawn-agents is ≤ 2 048 bytes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.spawn_agents]

_MAX_BYTES = 2048


def _repo_root() -> Path:
    """Locate the repo root from the test file's known position."""
    return Path(__file__).parent.parent.parent.parent.parent  # src/atdd/coach/commands/tests/ → repo root


def test_spawn_agents_launch_prompt_under_2kb() -> None:
    """build_wagon_launch_prompt('spawn-agents') output must be ≤ 2 048 bytes."""
    from atdd.coach.commands.issue_graph import build_wagon_launch_prompt  # type: ignore[import]

    repo = _repo_root()
    output = build_wagon_launch_prompt("spawn-agents", repo_root=repo)

    assert output is not None, (
        "build_wagon_launch_prompt returned None for 'spawn-agents'. "
        "The wagon directory plan/spawn_agents/ must be present."
    )

    byte_len = len(output.encode("utf-8"))
    assert byte_len <= _MAX_BYTES, (
        f"Output for 'spawn-agents' is {byte_len} bytes, exceeds 2 048-byte budget. "
        "Trim the output: use IDs rather than full descriptions, abbreviate WMBT list."
    )


def test_spawn_agents_launch_prompt_is_non_empty() -> None:
    """Output must be non-empty (guards against silent truncation)."""
    from atdd.coach.commands.issue_graph import build_wagon_launch_prompt  # type: ignore[import]

    repo = _repo_root()
    output = build_wagon_launch_prompt("spawn-agents", repo_root=repo)
    assert output, "Expected non-empty output for 'spawn-agents' wagon"


def test_unknown_wagon_returns_none() -> None:
    """build_wagon_launch_prompt returns None for a non-existent wagon (graceful degrade)."""
    from atdd.coach.commands.issue_graph import build_wagon_launch_prompt  # type: ignore[import]

    result = build_wagon_launch_prompt("wagon-that-does-not-exist", repo_root=_repo_root())
    assert result is None, (
        "Expected None for unknown wagon 'wagon-that-does-not-exist', "
        f"got: {result!r}"
    )
