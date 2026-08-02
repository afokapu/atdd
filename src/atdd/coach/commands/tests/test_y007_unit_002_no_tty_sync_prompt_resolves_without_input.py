# URN: test:integration-hardening:run-upgrade-unattended:Y007-UNIT-002-no-tty-sync-prompt-resolves-without-input
# Acceptance: acc:integration-hardening:Y007-UNIT-002-no-tty-sync-prompt-resolves-without-input
# WMBT: wmbt:integration-hardening:Y007
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""Y007-UNIT-002 — the second prompt is guarded too.

RED Test for acc:integration-hardening:Y007-UNIT-002-no-tty-sync-prompt-resolves-without-input
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:Y007
Purpose: With stdin not a terminal and only a stale local stamp to reconcile,
Upgrader.run() runs sync + init --force without asking 'Proceed? [Y/n]'. There
are two unguarded input() calls in upgrader.py, not one.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from atdd.coach.commands.upgrader import Upgrader

from ._upgrade_unattended_helpers import exploding_input, write_config

pytestmark = [pytest.mark.platform]


class _Ok:
    returncode = 0


@pytest.mark.platform
def test_y007_unit_002_no_tty_sync_prompt_resolves_without_input(tmp_path, monkeypatch):
    write_config(tmp_path, last_version="3.106.0")
    monkeypatch.chdir(tmp_path)

    calls = []

    def record(argv, **kwargs):
        calls.append(list(argv))
        return _Ok()

    with patch("atdd.coach.commands.upgrader.__version__", "4.27.0"), \
         patch("atdd.coach.commands.upgrader.subprocess.run", side_effect=record), \
         patch("sys.stdin.isatty", return_value=False), \
         patch("builtins.input", side_effect=exploding_input):
        rc = Upgrader(repo_root=tmp_path).run(yes=False, no_pypi=True)

    assert rc == 0, f"a no-TTY sync run must complete, got rc={rc}"

    joined = [" ".join(c) for c in calls]
    assert any("sync" in c for c in joined), f"atdd sync was not run; calls={joined}"
    assert any("init" in c and "--force" in c for c in joined), (
        f"atdd init --force was not run; calls={joined}"
    )
    sync_at = next(i for i, c in enumerate(joined) if "sync" in c)
    init_at = next(i for i, c in enumerate(joined) if "init" in c)
    assert sync_at < init_at, f"sync must precede init --force; calls={joined}"
