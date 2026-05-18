# URN: test:spawn-agents:smoke-persona-spawn-integrity:E005-SMOKE-001-real-green-to-smoke-spawn-creates-persona
# Acceptance: acc:spawn-agents:E005-SMOKE-001-real-green-to-smoke-spawn-creates-persona
# WMBT: wmbt:spawn-agents:E005
# Phase: SMOKE
# Layer: smoke
"""E005-SMOKE-001 — a real GREEN→SMOKE spawn against the live multiplexer
leaves a persona agent dir alongside the observer dir.

Against a real worktree, a real runtime directory, and the real multiplexer
backend (cmux / zellij / tmux) available on the host, driving the coach
GREEN→SMOKE spawn MUST leave ``.atdd/runtime/agents/`` with a persona dir
matching ``tester-<issue>-<suffix>/`` (with a written manifest) and the
matching ``tester-<issue>-<suffix>-observer/`` dir — and no observer dir
whose corresponding persona dir is absent.

This smoke test launches a real persona session, so it is opt-in: set
``ATDD_SMOKE_REAL_SPAWN=1`` to run it. It skips cleanly when the opt-in flag
is unset or no real multiplexer backend is available on the host.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _real_multiplexer_or_skip():
    """Resolve the real multiplexer backend, or skip if this smoke run is not
    opted in / no backend is available."""
    if os.environ.get("ATDD_SMOKE_REAL_SPAWN") != "1":
        pytest.skip(
            "ATDD_SMOKE_REAL_SPAWN != 1 — real GREEN→SMOKE persona spawn smoke "
            "is opt-in (it launches a live multiplexer session)"
        )
    try:
        from atdd.coach.utils.multiplexer import get_multiplexer

        return get_multiplexer()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no real multiplexer backend available on host: {exc}")


def _observer_without_persona(agents_dir: Path) -> list[str]:
    """Return observer dir names whose corresponding persona dir is absent."""
    if not agents_dir.is_dir():
        return []
    names = {d.name for d in agents_dir.iterdir() if d.is_dir()}
    orphans = []
    for name in names:
        if name.endswith("-observer"):
            persona = name[: -len("-observer")]
            if persona not in names:
                orphans.append(name)
    return orphans


def test_real_green_to_smoke_spawn_leaves_persona_alongside_observer(tmp_path):
    """A real GREEN→SMOKE spawn materialises both the persona dir (with a
    manifest) and its observer dir — never an observer without a persona."""
    backend = _real_multiplexer_or_skip()

    from atdd.coach.commands import spawn

    worktree = Path.cwd()
    runtime_root = tmp_path / ".atdd" / "runtime"
    issue = 733
    agent_id = f"tester-{issue}-{uuid.uuid4().hex[:8]}"

    spawn.cmd_spawn(
        persona="tester",
        llm="claude-code",
        worktree=worktree,
        issue=issue,
        agent_id=agent_id,
        runtime_root=runtime_root,
        phase="smoke",
        multiplexer=backend,
    )

    agents_dir = runtime_root / "agents"
    persona_dir = agents_dir / agent_id
    observer_dir = agents_dir / f"{agent_id}-observer"

    assert persona_dir.is_dir(), (
        f"real GREEN→SMOKE spawn left no persona dir: {persona_dir}"
    )
    assert (persona_dir / "manifest.json").is_file(), (
        f"persona dir has no written manifest: {persona_dir}"
    )
    assert observer_dir.is_dir(), (
        f"real GREEN→SMOKE spawn left no observer dir: {observer_dir}"
    )

    orphans = _observer_without_persona(agents_dir)
    assert not orphans, (
        f"observer dir(s) without a corresponding persona dir: {orphans} — "
        f"observer-without-persona must never occur (#733)"
    )
