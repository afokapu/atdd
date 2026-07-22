# URN: test:govern-lifecycle:cmux-native-worker-launcher:E043-SMOKE-001-live-cmux-native-launch-feed-no-shim
# Acceptance: acc:govern-lifecycle:E043-SMOKE-001-live-cmux-native-launch-feed-no-shim
# WMBT: wmbt:govern-lifecycle:E043
# Phase: SMOKE
"""acc:govern-lifecycle:E043-SMOKE-001 — LIVE smoke for the cmux-native launcher.

Proves, against a REAL cmux + claude (no fakes, no synthetic green — see the
#855 fake-green history), that the production launch builders boot a worker the
cmux-native way:

  1. ``cmux new-workspace --command 'claude "<tiny task>" --permission-mode
     acceptEdits --allowedTools Read'`` (built by build_agent_seed_argv +
     build_cmux_launch_argv) creates a worker surface with NO
     ``atdd.coach.shim`` / PersonaShim process in the launch path.
  2. The agent's POSITIONAL prompt auto-submits — the worker runs its first turn
     unattended (no paste, no submit sentinel).
  3. The worker's activity publishes to ``cmux rpc feed.list`` with
     ``source: claude`` (the cmux wrapper's Feed hooks are active WITHOUT the
     shim) — the same first-turn run is what produces the feed item, so a feed
     hit is joint proof of (2) and the Feed continuity acceptance.

Skips (never fakes) when cmux/claude are absent or the test is not running inside
a cmux session (new-workspace needs a window context). Run live with:

    PYTHONPATH=src <venv-python> -m pytest -s \
      src/atdd/coach/commands/tests/test_e043_smoke_001_live_cmux_native_launch.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from atdd.runtime.agent_control.cmux_launch import (
    build_agent_seed_argv,
    build_cmux_launch_argv,
)

pytestmark = [pytest.mark.platform]

_HAVE_CMUX = shutil.which("cmux") is not None
_HAVE_CLAUDE = shutil.which("claude") is not None
_IN_CMUX = bool(os.environ.get("CMUX_SURFACE_ID"))

pytestmark.append(
    pytest.mark.skipif(
        not (_HAVE_CMUX and _HAVE_CLAUDE and _IN_CMUX),
        reason="live cmux-native smoke needs cmux + claude on PATH inside a cmux session",
    )
)

# A tiny, tool-free task: the worker just has to take ONE unattended turn so the
# wrapper's Stop hook publishes a feed item. --allowedTools Read keeps it scoped.
_SEED_PROMPT = "Reply with exactly this token and nothing else: SMOKE-OK-978. Do not use any tools."
_FEED_TIMEOUT_S = float(os.environ.get("ATDD_SMOKE_FEED_TIMEOUT", "150"))
_POLL_S = 3.0

# Feed kinds that prove a TURN actually ran (the positional prompt auto-submitted
# and was processed) — as opposed to ``sessionStart``, which fires on mere boot
# and would NOT prove auto-submit. Requiring one of these keeps the smoke honest
# (#855 fake-green history): claude must have taken its first turn unattended.
_TURN_KINDS = frozenset({
    "stop", "userMessage", "userPromptSubmit", "assistantMessage",
    "toolUse", "toolResult", "notification",
})


def _feed_items() -> list[dict]:
    out = subprocess.run(
        ["cmux", "rpc", "feed.list"], capture_output=True, text=True, timeout=20
    )
    try:
        return json.loads(out.stdout or "{}").get("items", [])
    except json.JSONDecodeError:
        return []


def _shim_procs_for(tag: str) -> list[str]:
    """Return any process command lines that mention BOTH our worker tag and the
    pty shim — proof a shim is (wrongly) in this worker's launch path."""
    res = subprocess.run(["pgrep", "-fl", tag], capture_output=True, text=True)
    return [
        ln for ln in (res.stdout or "").splitlines()
        if "atdd.coach.shim" in ln or "PersonaShim" in ln or "atdd.runtime.agent_control" in ln
    ]


def _pre_trust_worktree(worktree_path: Path) -> None:
    """Mark *worktree_path* trusted in ~/.claude.json so the workspace-trust modal
    does not absorb the seed prompt.

    #1486: this was `commands.spawn._pre_trust_worktree`. Spawning left core, but the
    launch plane under test (runtime.agent_control.cmux_launch) did not — so the
    helper is inlined here as local test setup. Non-destructive; never raises.
    """
    env_override = os.environ.get("ATDD_CLAUDE_JSON_PATH")
    claude_json_path = Path(env_override) if env_override else Path.home() / ".claude.json"
    try:
        existing = json.loads(claude_json_path.read_text()) if claude_json_path.exists() else {}
        projects: dict = existing.setdefault("projects", {})
        projects.setdefault(str(worktree_path.resolve()), {})["hasTrustDialogAccepted"] = True
        claude_json_path.write_text(json.dumps(existing, indent=2))
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(f"⚠️  _pre_trust_worktree: could not write {claude_json_path}: {exc}")


def test_live_cmux_native_launch_seeds_and_publishes_to_feed_without_shim(tmp_path, capsys):
    tag = f"atdd-e043-smoke-{os.getpid()}"
    cwd = tmp_path / tag
    cwd.mkdir(parents=True, exist_ok=True)
    # Pre-trust so claude does not show the workspace-trust modal (which would
    # absorb the seed and the worker would never take its first turn).
    _pre_trust_worktree(cwd)

    # Build the launch the PRODUCTION way (prompt-first; --command wraps the agent).
    seed_argv = build_agent_seed_argv(
        "claude", _SEED_PROMPT, permission_mode="acceptEdits", allowed_tools=("Read",),
    )
    assert seed_argv[1] == _SEED_PROMPT, "prompt must be the positional seed"
    launch_argv = build_cmux_launch_argv(seed_argv, cwd=cwd, name=tag)
    assert launch_argv[:2] == ["cmux", "new-workspace"], launch_argv

    # The launch command itself carries NO shim — structural guarantee.
    command_str = launch_argv[launch_argv.index("--command") + 1]
    assert "atdd.coach.shim" not in command_str
    assert "atdd.runtime.agent_control" not in command_str
    assert command_str.split()[0] == "claude"

    workspace_ref = None
    try:
        launched = subprocess.run(launch_argv, capture_output=True, text=True, timeout=30)
        assert launched.returncode == 0, f"new-workspace failed: {launched.stderr!r}"
        # stdout shape: "OK workspace:N"
        workspace_ref = (launched.stdout or "").strip().split()[-1]
        assert workspace_ref.startswith("workspace:"), launched.stdout

        # No shim process exists for this worker's launch path.
        assert _shim_procs_for(tag) == [], (
            f"a shim process is in the cmux-native launch path: {_shim_procs_for(tag)!r}"
        )

        # The positional prompt auto-submitted → first turn runs → the wrapper
        # publishes turn activity to the Feed with source=claude. Poll for our
        # worker's cwd (match by unique tag to dodge the macOS /tmp ->
        # /private/tmp symlink). sessionStart alone is NOT enough — we require a
        # turn-activity kind, which only appears once the prompt was submitted
        # and processed (proving auto-submit, not mere boot).
        deadline = time.monotonic() + _FEED_TIMEOUT_S
        mine: list[dict] = []
        turn_hit = None
        while time.monotonic() < deadline and turn_hit is None:
            mine = [
                it for it in _feed_items()
                if tag in (it.get("cwd") or "") and it.get("source") == "claude"
            ]
            for it in mine:
                if it.get("kind") in _TURN_KINDS:
                    turn_hit = it
                    break
            if turn_hit is None:
                time.sleep(_POLL_S)

        kinds = sorted({it.get("kind") for it in mine})
        assert mine, (
            f"no feed.list item with source=claude for cwd containing {tag!r} within "
            f"{_FEED_TIMEOUT_S:.0f}s — the cmux wrapper Feed hooks did not fire without the shim"
        )
        assert turn_hit is not None, (
            f"the cmux-native worker published only {kinds!r} to the Feed but no "
            f"turn-activity kind ({sorted(_TURN_KINDS)}) within {_FEED_TIMEOUT_S:.0f}s — "
            f"the positional prompt did not auto-submit its first turn unattended"
        )

        # Evidence for docs/smoke-audit.md.
        print("\n[E043-SMOKE-001] LIVE cmux-native launch evidence")
        print(f"  workspace_ref : {workspace_ref}")
        print(f"  worker_cwd    : {cwd}")
        print(f"  launch_argv   : {launch_argv}")
        print(f"  feed_kinds    : {kinds}")
        print(f"  turn_item     : {json.dumps(turn_hit, sort_keys=True)}")
        print(f"  shim_in_path  : {_shim_procs_for(tag)}  (expected: [])")
    finally:
        if workspace_ref:
            subprocess.run(
                ["cmux", "close-workspace", "--workspace", workspace_ref],
                capture_output=True, text=True,
            )
