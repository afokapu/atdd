# URN: test:spawn-agents:persona-agent-id-env-injection:E005-SMOKE-001-real-spawn-persona-completes-phase-transition
# Acceptance: acc:spawn-agents:E005-SMOKE-001-real-spawn-persona-completes-phase-transition
# WMBT: wmbt:spawn-agents:E005
# Phase: SMOKE
# Layer: integration
# Harness: smoke/backend
"""E005-SMOKE-001 — a persona spawned by the real coach spawn path carries
``ATDD_AGENT_ID`` and completes a coach phase transition without any manual
``done.json`` emission.

SMOKE: no mocks of the unit under test. The real ``cmd_spawn`` (real
``_claude_code_adapter``, real prompt render) produces the launch command,
and the real installed ``atdd agent done`` console script runs as a
subprocess against a real runtime directory using exactly the environment
the spawn path injected.

RED: the real spawn path injects no ``ATDD_AGENT_ID``, so the real
``atdd agent done`` subprocess — given no ``--agent-id`` — exits non-zero
with ``agent id required`` and no ``done.json`` is written.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]

AGENT_ID = "coder-731-7f3d20ab"

SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-spawned-persona-missing-atdd-agent-id` |
"""


class FakeMultiplexer:
    """The only stand-in: a real GUI multiplexer cannot be driven in CI.
    The unit under test — the spawn-path command/env construction — is real."""

    name = "fake"

    def __init__(self) -> None:
        self._counter = 0
        self.commands: list[str] = []

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        return "workspace:1"

    def new_surface(self, command: Optional[str] = None, name: Optional[str] = None, **kw: Any) -> str:
        self._counter += 1
        self.commands.append(command or "")
        return f"surface:{self._counter}"

    def new_persona_surface(
        self, cwd: Any = None, command: Any = None, name: Any = None,
        *, observer_command: str = "", observer_name: str = "", **_: Any,
    ) -> str:
        persona_ref = self.new_surface(command=command, name=name)
        self.new_surface(command=observer_command, name=observer_name)
        return persona_ref

    def rename(self, ref: str, name: str) -> None:
        pass

    def send(self, ref: str, text: str) -> None:
        pass

    def send_key(self, ref: str, key: str) -> None:
        pass

    def paste_text(self, ref: str, text: str) -> None:
        pass

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""


def _env_from_command(command: str) -> dict[str, str]:
    return {
        m.group(1): m.group(3)
        for m in re.finditer(r"\b([A-Z][A-Z0-9_]*)=(['\"]?)([^\s'\"]*)\2", command)
    }


@pytest.mark.skipif(shutil.which("atdd") is None, reason="atdd CLI not on PATH")
def test_real_spawn_persona_completes_handshake_without_agent_id_flag(tmp_path, monkeypatch):
    from atdd.coach.commands import session_template, spawn

    # The GitHub API is the one boundary a hermetic CI run cannot cross, so
    # `fetch_issue` is stubbed for the same reason `FakeMultiplexer` stands in
    # for a GUI multiplexer. Everything else stays real: `compute_repo_short_name`
    # and `load_atdd_config` run unsubstituted against the real worktree config,
    # and the unit under test — the spawn-path env/command construction — is
    # exercised end to end.
    monkeypatch.setattr(  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2026-08-01
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": SAMPLE_BODY},
    )

    worktree = tmp_path / "feat-coach-spawned-persona-missing-atdd-agent-id"
    worktree.mkdir()
    runtime = tmp_path / "rt"
    result = spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=731,
        agent_id=AGENT_ID,
        runtime_root=runtime,
        multiplexer=FakeMultiplexer(),
    )

    # The environment the real spawn path injected into the persona process.
    injected = _env_from_command(result["command"])

    # Run the REAL `atdd agent done` console script as the persona would:
    # no --agent-id, only the spawn-injected environment.
    sub_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "ATDD_RUNTIME_ROOT": str(runtime),
    }
    if "ATDD_AGENT_ID" in injected:
        sub_env["ATDD_AGENT_ID"] = injected["ATDD_AGENT_ID"]

    proc = subprocess.run(
        ["atdd", "agent", "done", "--summary", "GREEN: smoke phase complete"],
        cwd=str(worktree),
        env=sub_env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, (
        f"atdd agent done failed from a spawned persona "
        f"(rc={proc.returncode}): {proc.stderr.strip()}"
    )
    done = runtime / "agents" / AGENT_ID / "done.json"
    assert done.exists(), (
        "done.json not written — the coach RuntimeWatcher would stall this phase forever"
    )
