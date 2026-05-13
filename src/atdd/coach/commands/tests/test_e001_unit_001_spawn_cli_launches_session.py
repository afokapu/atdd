# URN: test:spawn-agents:atdd-spawn-skeleton-and-harness:E001-UNIT-001-spawn-cli-launches-session
# Acceptance: acc:spawn-agents:E001-UNIT-001-spawn-cli-launches-session
# WMBT: wmbt:spawn-agents:E001
# Phase: RED
# Layer: application
"""E001-UNIT-001 — `atdd spawn` with the full required flag set launches a
session, writes ``<worktree>/.launch_prompt.txt``, dispatches a multiplexer
surface (ref returned and logged), and emits an ``agent_spawned`` runtime
event conforming to ``runtime-event.schema.json``.

Issue #499 — K1 spawn skeleton wrapping ``session_template.py::render``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import jsonschema
import pytest

import atdd

pytestmark = [pytest.mark.platform]

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
RUNTIME_EVENT_SCHEMA = (
    ATDD_PKG_DIR / "coach" / "schemas" / "runtime-event.schema.json"
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeMultiplexer:
    """Captures new_workspace / new_surface invocations for assertion."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._surface_counter = 0

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        ref = f"workspace:{len(self.calls) + 1}"
        self.calls.append(
            {"op": "new_workspace", "cwd": cwd, "command": command, "name": name, "ref": ref}
        )
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
        self.calls.append(
            {
                "op": "new_surface",
                "workspace_ref": workspace_ref,
                "pane_ref": pane_ref,
                "cwd": cwd,
                "command": command,
                "name": name,
                "ref": ref,
            }
        )
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


SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/spawn-test` |
| Train | `0002-coach-drives-lifecycle` |
| Feature | spawn skeleton sample |

## Scope

### Dependencies

- #1
"""


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_exposes_spawn_callable():
    from atdd.coach.commands import spawn

    assert callable(getattr(spawn, "cmd_spawn", None))
    assert callable(getattr(spawn, "main", None))
    assert callable(getattr(spawn, "run", None))


# ---------------------------------------------------------------------------
# CLI surface — required flag parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing_flag",
    ["--persona", "--llm", "--worktree", "--issue", "--agent-id", "--runtime"],
)
def test_required_flags_parse_without_error(missing_flag, tmp_path):
    """When all six required flags are provided, the parser MUST accept the
    invocation. When one is missing, argparse MUST reject it (exit 2)."""
    from atdd.coach.commands import spawn

    full_argv = [
        "--persona", "coder",
        "--llm", "claude-code",
        "--worktree", str(tmp_path / "wt"),
        "--issue", "358",
        "--agent-id", "coder-358-001",
        "--runtime", str(tmp_path / "rt"),
    ]
    parser = spawn._build_parser()
    parsed = parser.parse_args(full_argv)
    assert parsed.persona == "coder"
    assert parsed.llm == "claude-code"
    assert parsed.issue == 358
    assert parsed.agent_id == "coder-358-001"

    # Drop one flag at a time → parser must exit with non-zero.
    pruned = list(full_argv)
    idx = pruned.index(missing_flag)
    del pruned[idx : idx + 2]
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(pruned)
    assert exc.value.code != 0


# ---------------------------------------------------------------------------
# Behavior — launch prompt written, surface created, event emitted
# ---------------------------------------------------------------------------


def test_spawn_writes_launch_prompt_to_worktree(tmp_path, monkeypatch):
    from atdd.coach.commands import spawn
    from atdd.coach.commands import session_template

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "spawn skeleton sample", "body": SAMPLE_BODY},
    )

    worktree = tmp_path / "wt"
    worktree.mkdir()
    runtime = tmp_path / "rt"

    fake_mx = FakeMultiplexer()
    result = spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=358,
        agent_id="coder-358-001",
        runtime_root=runtime,
        multiplexer=fake_mx,
    )

    prompt_path = worktree / ".launch_prompt.txt"
    assert prompt_path.is_file()
    content = prompt_path.read_text()
    # render(context) substitutes the issue number into the template.
    assert "358" in content
    assert result["launch_prompt_path"] == prompt_path


def test_spawn_creates_multiplexer_surface_and_returns_ref(tmp_path, monkeypatch):
    from atdd.coach.commands import spawn
    from atdd.coach.commands import session_template

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": SAMPLE_BODY},
    )

    worktree = tmp_path / "wt"
    worktree.mkdir()
    runtime = tmp_path / "rt"

    fake_mx = FakeMultiplexer()
    result = spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=358,
        agent_id="coder-358-001",
        runtime_root=runtime,
        multiplexer=fake_mx,
    )
    assert any(c["op"] in ("new_workspace", "new_surface") for c in fake_mx.calls)
    assert result["surface_ref"]
    assert result["surface_ref"].startswith(("surface:", "workspace:"))


def test_spawn_emits_agent_spawned_event_conforming_to_schema(tmp_path, monkeypatch):
    from atdd.coach.commands import spawn
    from atdd.coach.commands import session_template

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": SAMPLE_BODY},
    )

    worktree = tmp_path / "wt"
    worktree.mkdir()
    runtime = tmp_path / "rt"

    fake_mx = FakeMultiplexer()
    spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=358,
        agent_id="coder-358-001",
        runtime_root=runtime,
        multiplexer=fake_mx,
    )

    events_path = runtime / "agents" / "coder-358-001" / "events.jsonl"
    assert events_path.is_file()
    lines = [ln for ln in events_path.read_text().splitlines() if ln.strip()]
    assert len(lines) >= 1
    record = json.loads(lines[0])

    schema = json.loads(RUNTIME_EVENT_SCHEMA.read_text())
    jsonschema.validate(record, schema)
    assert record["event_type"] == "agent_spawned"
    assert record["agent_id"] == "coder-358-001"


def test_spawn_required_flag_set_runs_without_error_via_main(tmp_path, monkeypatch, capsys):
    """End-to-end: ``atdd.coach.commands.spawn.main([...])`` succeeds when
    invoked with the required flag set."""
    from atdd.coach.commands import spawn
    from atdd.coach.commands import session_template

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": SAMPLE_BODY},
    )

    fake_mx = FakeMultiplexer()
    monkeypatch.setattr(spawn, "_resolve_multiplexer", lambda preferred=None: fake_mx)

    worktree = tmp_path / "wt"
    worktree.mkdir()
    runtime = tmp_path / "rt"

    rc = spawn.main([
        "--persona", "coder",
        "--llm", "claude-code",
        "--worktree", str(worktree),
        "--issue", "358",
        "--agent-id", "coder-358-001",
        "--runtime", str(runtime),
    ])
    assert rc == 0
    # The surface ref must surface to stdout/log so observers can correlate.
    captured = capsys.readouterr()
    assert "surface" in (captured.out + captured.err).lower()
