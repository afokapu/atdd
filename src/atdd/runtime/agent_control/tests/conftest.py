"""Shared fixtures for runtime.agent_control controller tests (#969)."""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.runtime.agent_control import DispatchSpec


@pytest.fixture
def make_spec(tmp_path: Path):
    """Factory for a DispatchSpec with overridable permission policy fields.

    The launch-permission-policy is carried *entirely* by the spec fields
    (OS-1a, #969): ``permission_mode`` + ``allowed_tools``. Tests vary those to
    assert the cli-return launch command derives from them, never from a
    hardcoded forbidden flag.
    """

    def _make(
        *,
        permission_mode: str = "acceptEdits",
        allowed_tools: tuple[str, ...] = (
            "Bash",
            "Edit",
            "Write",
            "Read",
            "TodoWrite",
            "Glob",
            "Grep",
            "WebFetch",
        ),
    ) -> DispatchSpec:
        return DispatchSpec(
            agent_id="agent-1",
            persona="coder",
            worktree_path=tmp_path / "wt",
            prompt_text="do the thing",
            correction_inbox=tmp_path / "runtime" / "cli-return.jsonl",
            output_log=tmp_path / "runtime" / "output.log",
            runtime_dir=tmp_path / "runtime",
            env_overrides={},
            transport="cli-return",
            permission_mode=permission_mode,  # type: ignore[arg-type]
            allowed_tools=allowed_tools,
        )

    return _make
