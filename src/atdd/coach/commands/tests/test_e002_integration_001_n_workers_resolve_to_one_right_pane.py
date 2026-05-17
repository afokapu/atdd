# URN: test:consolidate-coach-workspace:wire-layout-into-spawn-path:E002-INTEGRATION-001-n-workers-resolve-to-one-right-pane
# Acceptance: acc:consolidate-coach-workspace:E002-INTEGRATION-001-n-workers-resolve-to-one-right-pane
# WMBT: wmbt:consolidate-coach-workspace:E002
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E002-INTEGRATION-001 — dispatching N workers through the real ``cmd_spawn``
yields exactly one right worker pane holding N surfaces and zero extra panes.

RED: each ``cmd_spawn`` opens its own tiled pane (``new_persona_surface``), so
N issues produce N panes — exactly the pre-#736 proliferation. This test pins
the wired contract: ``resolve_or_create_coach_surface`` creates the single
worker-hosting pane once, and every worker is added into it as a surface via
``add_worker_surface``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]


_SURFACE_OPS = ("new_surface",)
_TILED_PANE_OPS = ("new_persona_surface", "new_pane", "split_pane")

SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-workspace-layout-not-wired-into-spawn-path` |
| Train | none |
| Feature | wire layout into spawn path |
"""


class FakeMx:
    """Multiplexer double — records calls, separates surface creation from
    pane creation, and reflects created workspaces in ``list_panes`` so
    ``resolve_or_create_coach_surface`` can resolve-or-create idempotently."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._n = 0

    def _rec(self, op: str, name: Any = None) -> str:
        self._n += 1
        ref = f"{op}:{self._n}"
        self.calls.append({"op": op, "name": name, "ref": ref})
        return ref

    def new_workspace(self, cwd: Any = None, command: Any = None,
                      name: Optional[str] = None) -> str:
        return self._rec("new_workspace", name)

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None, name: Any = None,
                    direction: Any = None) -> str:
        return self._rec("new_surface", name)

    def new_persona_surface(self, cwd: Any = None, command: Any = None,
                            name: Any = None, **_: Any) -> str:
        return self._rec("new_persona_surface", name)

    def new_pane(self, *a: Any, **k: Any) -> str:
        return self._rec("new_pane")

    def split_pane(self, *a: Any, **k: Any) -> str:
        return self._rec("split_pane")

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

    def list_panes(self) -> list[dict]:
        return [{"name": c["name"], "ref": c["ref"]}
                for c in self.calls if c["op"] == "new_workspace"]

    def count(self, *ops: str) -> int:
        return sum(1 for c in self.calls if c["op"] in ops)


def _spawn(tmp_path: Path, monkeypatch, fake_mx: FakeMx, issue: int) -> dict:
    """Drive the real ``cmd_spawn`` for one issue against ``fake_mx``."""
    from atdd.coach.commands import spawn
    from atdd.coach.commands import session_template

    monkeypatch.setattr(
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": SAMPLE_BODY},
    )
    monkeypatch.setattr(spawn, "compute_repo_short_name",
                        lambda config: "ATDD", raising=False)
    monkeypatch.setattr(spawn, "load_atdd_config",
                        lambda root: {"repo": {"short_name": "ATDD"}},
                        raising=False)
    monkeypatch.setattr(spawn, "capture_session_uuid",
                        lambda **kw: None, raising=False)

    worktree = tmp_path / f"wt-{issue}"
    worktree.mkdir(exist_ok=True)
    return spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=issue,
        agent_id=f"coder-{issue}-001",
        runtime_root=tmp_path / "rt",
        multiplexer=fake_mx,
    )


def test_five_workers_resolve_to_one_right_pane(tmp_path, monkeypatch):
    """Five ``cmd_spawn`` invocations resolve to exactly one worker pane
    holding five surfaces — not five tiled panes."""
    fake_mx = FakeMx()
    issues = [736, 601, 730, 741, 745]

    for issue in issues:
        _spawn(tmp_path, monkeypatch, fake_mx, issue)

    surfaces = fake_mx.count(*_SURFACE_OPS)
    assert surfaces == len(issues), (
        f"expected exactly {len(issues)} worker surfaces (one per issue); got "
        f"{surfaces} — workers are not being added via add_worker_surface"
    )
    tiled = fake_mx.count(*_TILED_PANE_OPS)
    assert tiled == 0, (
        f"the spawn path opened {tiled} tiled pane(s) "
        f"({[c['op'] for c in fake_mx.calls if c['op'] in _TILED_PANE_OPS]}); "
        f"{len(issues)} issues must resolve to ONE right pane, not {tiled} panes"
    )
    worker_panes = fake_mx.count("new_workspace")
    assert worker_panes == 1, (
        f"resolve_or_create_coach_surface created {worker_panes} worker "
        f"pane(s) across {len(issues)} spawns; it must resolve-or-create "
        f"exactly one (the second spawn onward reuses the existing pane)"
    )
