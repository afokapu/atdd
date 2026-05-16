# URN: test:spawn-agents:transactional-spawn-and-orphan-pane-gc:E003-UNIT-001-close-on-rename-failure
# Acceptance: acc:spawn-agents:E003-UNIT-001-close-on-rename-failure
# WMBT: wmbt:spawn-agents:E003
# Phase: RED
# Layer: application
"""E003-UNIT-001 — a failure in apply_canonical_name_and_layout closes the surface.

The spawn pipeline runs `new_surface` then `apply_canonical_name_and_layout`
(the rename + layout pass). When that pass raises, the transactional spawn
pipeline MUST close the surface created earlier in the same attempt before
re-raising — otherwise the surface is orphaned.

A `FakeMultiplexer` isolates the test from any real cmux daemon: it raises
inside `rename` (the step apply_canonical_name_and_layout drives) and
records every `close` call.

RED: today `cmd_spawn` does not wrap the post-creation steps in a
close-on-failure guard, so the surface is never closed when the layout
pass blows up.

Issue #655 — Layer 1: transactional spawn pipeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]


SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-spawn-orphan-pane-cleanup` |
| Train | `0002-coach-drives-lifecycle` |
| Feature | orphan pane cleanup sample |
"""


class FakeMultiplexer:
    """Records new_surface / rename / close; raises a propagating error
    inside `rename` so apply_canonical_name_and_layout fails hard."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._surface_counter = 0

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        ref = f"workspace:{len(self.calls) + 1}"
        self.calls.append({"op": "new_workspace", "cwd": cwd, "command": command, "name": name, "ref": ref})
        return ref

    def new_surface(
        self,
        workspace_ref: Optional[str] = None,
        pane_ref: Optional[str] = None,
        cwd: Optional[str] = None,
        command: Optional[str] = None,
        name: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> str:
        self._surface_counter += 1
        ref = f"surface:{self._surface_counter}"
        self.calls.append({"op": "new_surface", "cwd": cwd, "command": command, "name": name, "ref": ref})
        return ref

    def new_persona_surface(
        self,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        *,
        observer_runtime_root: str = "",
        observer_agent_id: str = "",
        observer_name: str = "",
        observer_command: str = "",
        **_: Any,
    ) -> str:
        persona_ref = self.new_surface(cwd=cwd, command=command, name=name)
        try:
            self.new_surface(cwd=cwd, command=observer_command, name=observer_name)
        except Exception:
            pass
        return persona_ref

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})
        # A hard failure in the rename/layout step — NOT a recoverable
        # MultiplexerError, so it propagates out of the layout pass.
        raise RuntimeError("simulated apply_canonical_name_and_layout failure")

    def close(self, ref: str) -> None:
        self.calls.append({"op": "close", "ref": ref})

    def send(self, ref: str, text: str) -> None:
        self.calls.append({"op": "send", "ref": ref, "text": text})

    def send_key(self, ref: str, key: str) -> None:
        self.calls.append({"op": "send_key", "ref": ref, "key": key})

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""


def _spawn(tmp_path: Path, monkeypatch, fake_mx: FakeMultiplexer):
    from atdd.coach.commands import spawn
    from atdd.coach.commands import session_template

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": SAMPLE_BODY},
    )
    monkeypatch.setattr(spawn, "compute_repo_short_name", lambda config: "ATDD", raising=False)
    monkeypatch.setattr(
        spawn, "load_atdd_config", lambda root: {"repo": {"short_name": "ATDD"}}, raising=False
    )

    worktree = tmp_path / "feat-coach-spawn-orphan-pane-cleanup"
    worktree.mkdir(exist_ok=True)
    runtime = tmp_path / "rt"
    return spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=655,
        agent_id="coder-655-001",
        runtime_root=runtime,
        multiplexer=fake_mx,
    )


def test_layout_failure_closes_the_spawned_surface(tmp_path, monkeypatch):
    """When apply_canonical_name_and_layout raises, the spawn pipeline
    must record a close() for the surface it created, then re-raise."""
    fake_mx = FakeMultiplexer()

    with pytest.raises(RuntimeError, match="apply_canonical_name_and_layout"):
        _spawn(tmp_path, monkeypatch, fake_mx)

    rename_calls = [c for c in fake_mx.calls if c["op"] == "rename"]
    assert rename_calls, "expected the spawn pipeline to attempt a rename"

    close_calls = [c for c in fake_mx.calls if c["op"] == "close"]
    assert close_calls, (
        "orphan surface leaked: apply_canonical_name_and_layout failed but "
        "the spawn pipeline never called close() on the surface it created. "
        f"recorded calls: {fake_mx.calls}"
    )

    failed_ref = rename_calls[0]["ref"]
    assert any(c["ref"] == failed_ref for c in close_calls), (
        f"close() targeted the wrong surface — the surface whose rename "
        f"failed ({failed_ref}) must be the one closed. close calls: {close_calls}"
    )
