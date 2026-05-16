# URN: test:coach-wave-orchestration:within-wave-concurrency-and-pane-identity:D001-UNIT-002-spawn-site-passes-persona
# Acceptance: acc:coach-wave-orchestration:D001-UNIT-002-spawn-site-passes-persona
# WMBT: wmbt:coach-wave-orchestration:D001
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""D001-UNIT-002 — the spawn site passes the persona/phase into
``compute_canonical_name`` rather than computing a per-issue-only name.

RED: ``commands/spawn.py`` calls ``compute_canonical_name(repo_short, issue,
slug)`` with no persona/phase argument, so every persona pane of an issue gets
the identical name. This test patches ``compute_canonical_name`` to record the
arguments the spawn site actually passes.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]


SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-within-wave-serial-execution` |
| Train | `none` |
| Feature | persona pane identity |
"""


class FakePaneMx:
    """Minimal pane-mode multiplexer double — records surface creation."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._n = 0

    def _ref(self) -> str:
        self._n += 1
        return f"pane:{self._n}"

    def new_persona_surface(
        self, cwd: Any = None, command: Any = None, name: Any = None,
        *, observer_runtime_root: str = "", observer_agent_id: str = "",
        observer_name: str = "", observer_command: str = "", **_: Any,
    ) -> str:
        ref = self._ref()
        self.calls.append({"op": "new_persona_surface", "name": name, "ref": ref})
        return ref

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None, name: Any = None,
                    direction: Any = None) -> str:
        ref = self._ref()
        self.calls.append({"op": "new_surface", "name": name, "ref": ref})
        return ref

    def new_workspace(self, cwd: Any = None, command: Any = None,
                      name: Optional[str] = None) -> str:
        ref = self._ref()
        self.calls.append({"op": "new_workspace", "name": name, "ref": ref})
        return ref

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})

    def send(self, ref: str, text: str) -> None:
        self.calls.append({"op": "send", "ref": ref, "text": text})

    def send_key(self, ref: str, key: str) -> None:
        self.calls.append({"op": "send_key", "ref": ref, "key": key})

    def paste_text(self, ref: str, text: str) -> None:
        self.calls.append({"op": "paste_text", "ref": ref})

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""


def _persona_phase_arg(args, kwargs):
    """Return whatever persona/phase segment was passed beyond the 3 base args."""
    return kwargs.get("persona") or kwargs.get("phase") or (
        args[3] if len(args) > 3 else None
    )


def test_spawn_site_passes_persona_into_canonical_name(tmp_path, monkeypatch):
    """``cmd_spawn`` computes the pane name with a non-empty persona/phase arg."""
    from atdd.coach.commands import spawn as cmd_spawn_mod
    from atdd.coach.commands import session_template

    recorded: list[tuple] = []

    def recording_canonical(*args, **kwargs):
        recorded.append((args, kwargs))
        seg = _persona_phase_arg(args, kwargs)
        return f"ATDD730-{seg or 'noseg'}-coach-within-wave"

    monkeypatch.setattr(cmd_spawn_mod, "compute_canonical_name", recording_canonical)
    monkeypatch.setattr(
        cmd_spawn_mod, "compute_repo_short_name", lambda config: "ATDD",
        raising=False,
    )
    monkeypatch.setattr(
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "persona pane identity", "body": SAMPLE_BODY},
    )

    fake_mx = FakePaneMx()
    worktree = tmp_path / "feat-coach-within-wave-serial-execution"
    worktree.mkdir()

    result = cmd_spawn_mod.cmd_spawn(
        persona="tester",
        llm="claude-code",
        worktree=worktree,
        issue=730,
        agent_id="tester-730-001",
        runtime_root=tmp_path / "rt",
        phase="red",
        persona_prompt_content="",
        multiplexer=fake_mx,
        multiplexer_mode="pane",
    )

    assert recorded, "compute_canonical_name was never called at the spawn site"
    args, kwargs = recorded[-1]
    seg = _persona_phase_arg(args, kwargs)
    assert seg, (
        "the spawn site called compute_canonical_name with no persona/phase "
        f"segment (args={args}, kwargs={kwargs}) — every persona pane of the "
        "issue receives an identical per-issue-only name"
    )
    # The pane name actually used for the launch matches the persona-qualified
    # return value.
    assert result["canonical_name"] == f"ATDD730-{seg}-coach-within-wave"
