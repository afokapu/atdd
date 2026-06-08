# URN: test:mediate-worker-decisions:coach-runtime:M005-UNIT-001-run-cmux-raises-and-loud-logs-on-nonzero-exit-not-swallowed
# Acceptance: acc:mediate-worker-decisions:M005-UNIT-001-run-cmux-raises-and-loud-logs-on-nonzero-exit-not-swallowed
# WMBT: wmbt:mediate-worker-decisions:M005
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""M005-UNIT-001 — run_cmux surfaces a non-zero cmux exit instead of swallowing it.

The #1007 root cause: a detached daemon's ``cmux rpc`` failed with a broken-pipe
write error, and ``run_cmux`` returned ``""`` (ignoring returncode + stderr) — so
the daemon saw an empty Feed every poll and silently never decided. ``run_cmux``
must STOP swallowing: on a non-zero cmux exit it loud-logs and raises a typed
``CmuxCommandError`` carrying the argv/returncode/stderr, so a broken Feed
connection is visible (in daemon.log) rather than masquerading as empty output.
"""
from __future__ import annotations

import logging
import subprocess

import pytest

from atdd.mediate_worker_decisions.commons import cmux_cli
from atdd.mediate_worker_decisions.commons.cmux_cli import CmuxCommandError, run_cmux


def test_run_cmux_raises_and_loud_logs_on_nonzero_exit(monkeypatch, caplog):
    def _broken_pipe(argv, **kwargs):
        # cmux's broken-pipe failure mode: non-zero exit, no stdout, errno-32 on stderr.
        return subprocess.CompletedProcess(
            argv,
            returncode=1,
            stdout="",
            stderr="Error: Failed to write to socket (Broken pipe, errno 32)",
        )

    monkeypatch.setattr(cmux_cli.subprocess, "run", _broken_pipe)

    with caplog.at_level(logging.WARNING, logger=cmux_cli._log.name):
        with pytest.raises(CmuxCommandError) as excinfo:
            run_cmux("rpc", "feed.list", "{}")

    # The failure is SURFACED, not swallowed into "".
    err = excinfo.value
    assert err.returncode == 1
    assert "Broken pipe" in err.stderr

    # And it is loud — a WARNING+ record names the cmux failure for daemon.log.
    loud = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert loud, "a non-zero cmux exit must be loud-logged, never silently swallowed"
    assert any("cmux" in r.getMessage().lower() for r in loud)
