# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:Y001-UNIT-001-default-timeout-is-30s
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y001-UNIT-001-default-timeout-is-30s
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y001
# Phase: RED
# Layer: application
# Runtime: python
"""Y001-UNIT-001 — _get_worker_ready_timeout returns 30 when ATDD_WORKER_READY_TIMEOUT not set.

RED: _get_worker_ready_timeout does not exist in spawn.py. The timeout is
inlined as the literal string "10.0" in os.environ.get() calls throughout the
file, making it impossible to test the default in isolation. Fresh worktrees
regularly take 20-40s to boot, causing spurious WorkerReadinessTimeout errors.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_default_timeout_is_30_seconds():
    """_get_worker_ready_timeout returns 30 when env var is not set."""
    from atdd.coach.commands import spawn

    fn = getattr(spawn, "_get_worker_ready_timeout", None)
    assert fn is not None, (
        "spawn._get_worker_ready_timeout is not implemented — "
        "the timeout default is still hardcoded to 10s (RED)"
    )

    result = fn(env={})
    assert result == 30, (
        f"default timeout must be 30 seconds; got {result!r}"
    )


def test_env_override_respected():
    """_get_worker_ready_timeout returns the env var value when set."""
    from atdd.coach.commands import spawn

    fn = getattr(spawn, "_get_worker_ready_timeout", None)
    assert fn is not None, "spawn._get_worker_ready_timeout is not implemented (RED)"

    result = fn(env={"ATDD_WORKER_READY_TIMEOUT": "60"})
    assert result == 60, (
        f"timeout from env must be 60; got {result!r}"
    )
