# URN: test:reconcile-local-store:trigger-head-hooks:M001-UNIT-001-head-moving-hooks-invoke-reconcile
# Acceptance: acc:reconcile-local-store:M001-UNIT-001-head-moving-hooks-invoke-reconcile
# WMBT: wmbt:reconcile-local-store:M001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: post-merge, post-checkout, post-rewrite and pre-rebase each invoke `atdd state reconcile` exactly once for the new HEAD; pre-rebase additionally runs the dirty-store check; and a failing hook reports without blocking the git operation. Refs #1400.
"""Every HEAD-moving operation reconciles (M001-UNIT-001).

wagon: reconcile-local-store | feature: trigger-head-hooks | phase: RED
WMBT: wmbt:reconcile-local-store:M001

Merge, checkout, rebase and amend all move HEAD, which means the committed projection —
the shared truth the local store is anchored to — has changed underneath it. Each gets a
hook, and each hook calls the same one command.

The hooks are run as real shell scripts here, against a recorded spy standing in for the
``atdd`` binary. What is being pinned is that a hook *cannot block git*: it exits 0 even
when reconcile fails, because a hook that can wedge a merge has been promoted from
convenience to authority, and spec §9 is explicit that it must never be. Refs #1400.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List

import pytest

#: The hook templates `atdd init` installs, and the git operation each answers to.
_HOOK_TEMPLATES = Path(__file__).resolve().parents[3] / "coach" / "templates" / "hooks"

#: HEAD-moving operation → (hook name, the argv git passes it).
_HEAD_MOVING = {
    "merge": ("post-merge", ["0"]),
    "checkout": ("post-checkout", ["abc123", "def456", "1"]),
    "amend": ("post-rewrite", ["amend"]),
    "rebase": ("pre-rebase", ["main"]),
}


def _spy(tmp_path: Path, *, exit_code: int = 0) -> Path:
    """A fake ``atdd`` on PATH that records every invocation and returns ``exit_code``.

    The log starts empty on every call, so a re-armed spy counts only its own run.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    log = tmp_path / "invocations.log"
    log.unlink(missing_ok=True)
    spy = bindir / "atdd"
    spy.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    spy.chmod(0o755)
    return log


def _run_hook(hook: str, argv: List[str], tmp_path: Path) -> subprocess.CompletedProcess:
    env = {
        "PATH": f"{tmp_path / 'bin'}:{os.environ.get('PATH', '')}",
        "HOME": str(tmp_path),
    }  # CI is deliberately unset: the hooks no-op under CI=true, and we want the body.
    return subprocess.run(
        ["sh", str(_HOOK_TEMPLATES / hook), *argv],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=60,
    )


def _invocations(log: Path) -> List[str]:
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


@pytest.mark.parametrize("operation", sorted(_HEAD_MOVING))
def test_m001_unit_001_head_moving_hooks_invoke_reconcile(tmp_path, operation) -> None:
    """Each HEAD-moving operation triggers exactly one reconcile, and never blocks git."""
    hook, argv = _HEAD_MOVING[operation]
    log = _spy(tmp_path)

    result = _run_hook(hook, argv, tmp_path)

    # Every HEAD-moving operation triggers exactly one reconcile invocation.
    calls = _invocations(log)
    reconciles = [call for call in calls if call.startswith("state reconcile")]
    assert len(reconciles) == 1, f"{hook} made {len(reconciles)} reconcile calls: {calls}"
    assert result.returncode == 0

    # pre-rebase additionally runs the dirty-store protection check.
    if hook == "pre-rebase":
        assert reconciles == ["state reconcile --check-dirty"]
    else:
        assert reconciles == ["state reconcile"]

    # A hook failure reports but does not block the underlying git operation.
    failing = _spy(tmp_path, exit_code=1)
    failed = _run_hook(hook, argv, tmp_path)
    assert failed.returncode == 0, f"{hook} blocked git on a reconcile failure"
    assert len(_invocations(failing)) == 1


def test_m001_unit_001_post_checkout_ignores_file_checkouts(tmp_path) -> None:
    """A file checkout does not move HEAD, so it must not reconcile."""
    log = _spy(tmp_path)

    # git passes 0 as the third argument for a file checkout (`git checkout -- path`).
    result = _run_hook("post-checkout", ["abc123", "abc123", "0"], tmp_path)

    assert result.returncode == 0
    assert _invocations(log) == []
