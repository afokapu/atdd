# URN: test:govern-lifecycle:extract-runtime-agent-control-and-close-spawn-cluster:E039-UNIT-002-deliver-prompt-injects-and-submits
# Acceptance: acc:govern-lifecycle:E039-UNIT-002-deliver-prompt-injects-and-submits
# WMBT: wmbt:govern-lifecycle:E039
# Phase: RED
# Assertion: behavioral
# Layer: runtime
"""E039-UNIT-002 — deliver_prompt injects AND submits (closes #872).

docs/coach-decomposition.md §4.8: ``deliver_prompt`` "MUST inject AND submit".
The proper integration check drains cli-return.jsonl directly (NOT cmux paste):
the controller writes the prompt to the correction inbox; the shim drains it and
delivers the prompt bytes terminated by the submit sentinel.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _make_spec(runtime_dir: Path, agent_id: str):
    from atdd.runtime.agent_control import DispatchSpec

    agent_dir = runtime_dir / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    return DispatchSpec(
        agent_id=agent_id,
        persona="coder",
        worktree_path=runtime_dir,
        prompt_text="launch",
        correction_inbox=agent_dir / "cli-return.jsonl",
        output_log=agent_dir / "output.log",
        runtime_dir=runtime_dir,
        env_overrides={},
        transport="cli-return",
        permission_mode="acceptEdits",
        allowed_tools=(),
    )


def test_deliver_prompt_appends_correction_row(tmp_path):
    from atdd.runtime.agent_control import ShimAgentController

    controller = ShimAgentController()
    spec = _make_spec(tmp_path, "coder-872-a")
    handle = controller.prepare(spec)

    controller.deliver_prompt(handle, "implement the feature")

    rows = [
        json.loads(line)
        for line in spec.correction_inbox.read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    assert rows[0]["correction_text"] == "implement the feature"


def test_delivered_prompt_drains_with_submit_sentinel(tmp_path):
    """The drained delivery carries the prompt bytes AND the submit sentinel."""
    from atdd.runtime.agent_control import PersonaShim, ShimAgentController

    controller = ShimAgentController()
    spec = _make_spec(tmp_path, "coder-872-b")
    handle = controller.prepare(spec)
    controller.deliver_prompt(handle, "do it now")

    captured: list[bytes] = []
    shim = PersonaShim(
        agent_id="coder-872-b",
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=captured.append,
    )
    shim.poll_once()

    assert captured == [b"do it now\n"], captured
    # Negative guard: the prompt is never delivered without a submit terminator.
    assert all(chunk.endswith(b"\n") for chunk in captured)
