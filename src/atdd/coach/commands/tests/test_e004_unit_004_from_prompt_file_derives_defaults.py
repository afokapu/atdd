# URN: test:spawn-agents:atdd-spawn-skeleton-and-harness:E004-UNIT-004-from-prompt-file-derives-defaults
# Acceptance: acc:spawn-agents:E004-UNIT-004-from-prompt-file-derives-defaults
# WMBT: wmbt:spawn-agents:E004
# Phase: RED
# Layer: application
"""E004-UNIT-004 — ``atdd spawn --from-prompt-file <path> --worktree <wt>
--issue <N>`` derives ``--persona`` / ``--llm`` / ``--agent-id`` / ``--runtime``
from wagon-manifest defaults plus per-issue conventions, so the cwd-correct
launch path needs only 3 flags instead of 6.

Issue #662 — the high flag burden of ``atdd spawn`` (6 required flags) pushes
operators toward the unsafe ``cmux send "claude ..."`` shortcut. This
convenience variant is the Layer-C carrot: it shrinks the ergonomic gap so the
cwd-correct path is the reflex. The launched surface's cwd MUST still equal the
worktree — the convenience flag does not weaken the cwd guarantee.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest


# --------------------------------------------------------------------------
# Known-good fake multiplexer (mirrors the E001 spawn-skeleton fake): captures
# new_workspace / new_surface invocations, including the ``cwd`` each surface
# is bound to.
# --------------------------------------------------------------------------
class FakeMultiplexer:
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
| Branch | `feat/reject-raw-cmux-claude-spawn` |
| Train | `0002-coach-drives-lifecycle` |
| Feature | spawn skeleton sample |

## Scope

### Dependencies

- #1
"""


# --------------------------------------------------------------------------
# CLI surface — the --from-prompt-file flag and reduced required-flag set
# --------------------------------------------------------------------------


def test_from_prompt_file_flag_is_registered():
    """``atdd spawn`` must register a ``--from-prompt-file`` option."""
    from atdd.coach.commands import spawn

    parser = spawn._build_parser()
    option_strings = {s for action in parser._actions for s in action.option_strings}
    assert "--from-prompt-file" in option_strings


def test_three_flag_invocation_parses_without_the_other_four(tmp_path):
    """With ``--from-prompt-file``, the parser must NOT require ``--persona``,
    ``--llm``, ``--agent-id`` or ``--runtime``."""
    from atdd.coach.commands import spawn

    prompt = tmp_path / "p.md"
    prompt.write_text("do the thing")

    parser = spawn._build_parser()
    parsed = parser.parse_args(
        [
            "--from-prompt-file", str(prompt),
            "--worktree", str(tmp_path / "wt"),
            "--issue", "999",
        ]
    )
    assert parsed.issue == 999
    assert Path(parsed.from_prompt_file) == prompt


def test_full_required_flag_set_still_parses(tmp_path):
    """Regression — the existing explicit 6-flag path is unaffected."""
    from atdd.coach.commands import spawn

    parser = spawn._build_parser()
    parsed = parser.parse_args(
        [
            "--persona", "coder",
            "--llm", "claude-code",
            "--worktree", str(tmp_path / "wt"),
            "--issue", "358",
            "--agent-id", "coder-358-001",
            "--runtime", str(tmp_path / "rt"),
        ]
    )
    assert parsed.persona == "coder"
    assert parsed.issue == 358


# --------------------------------------------------------------------------
# Behaviour — a 3-flag launch derives the rest and binds the worktree cwd
# --------------------------------------------------------------------------


def test_from_prompt_file_launch_binds_worktree_as_cwd(tmp_path, monkeypatch):
    """End-to-end: a 3-flag ``atdd spawn --from-prompt-file`` invocation
    launches successfully — the four omitted flags are derived — and every
    surface it creates is bound to the worktree cwd."""
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
    prompt = tmp_path / "p.md"
    prompt.write_text("launch prompt body")

    rc = spawn.run(
        [
            "--from-prompt-file", str(prompt),
            "--worktree", str(worktree),
            "--issue", "999",
        ]
    )
    assert rc == 0

    surface_calls = [c for c in fake_mx.calls if c["op"] in ("new_workspace", "new_surface")]
    assert surface_calls, "expected at least one multiplexer surface to be created"
    # The cwd-correct guarantee of `atdd spawn` is preserved by the convenience flag.
    assert all(c["cwd"] == str(worktree) for c in surface_calls)
