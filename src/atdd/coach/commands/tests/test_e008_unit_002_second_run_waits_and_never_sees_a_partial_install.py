# URN: test:integration-hardening:run-upgrade-unattended:E008-UNIT-002-second-run-waits-and-never-sees-a-partial-install
# Acceptance: acc:integration-hardening:E008-UNIT-002-second-run-waits-and-never-sees-a-partial-install
# WMBT: wmbt:integration-hardening:E008
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E008-UNIT-002 — two concurrent runs serialise rather than interleave.

RED Test for acc:integration-hardening:E008-UNIT-002-second-run-waits-and-never-sees-a-partial-install
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:E008
Purpose: ~60 agents share one pipx install. Y007 makes the upgrade reachable to
all of them, which makes concurrent mutation reachable too. The mutating
sections must not overlap.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from atdd.coach.commands.upgrader import Upgrader

from ._upgrade_unattended_helpers import write_config

pytestmark = [pytest.mark.platform]


@pytest.mark.platform
def test_e008_unit_002_mutating_sections_do_not_overlap(tmp_path, monkeypatch):
    repo_a = tmp_path / "worktree-a"
    repo_b = tmp_path / "worktree-b"
    for repo in (repo_a, repo_b):
        repo.mkdir(parents=True)
        write_config(repo, last_version="3.106.0")

    intervals = []
    intervals_lock = threading.Lock()

    def slow_upgrade():
        entered = time.monotonic()
        time.sleep(0.25)
        left = time.monotonic()
        with intervals_lock:
            intervals.append((entered, left))
        return True

    results = {}

    def run_one(name, repo):
        with patch("atdd.coach.commands.upgrader.__version__", "3.106.0"), \
             patch(
                 "atdd.coach.commands.upgrader.is_outdated",
                 return_value=(True, "3.106.0", "4.27.0"),
             ), \
             patch("atdd.coach.commands.upgrader.auto_upgrade", side_effect=slow_upgrade):
            results[name] = Upgrader(repo_root=repo).run(yes=True)

    threads = [
        threading.Thread(target=run_one, args=("a", repo_a)),
        threading.Thread(target=run_one, args=("b", repo_b)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(intervals) == 2, f"both runs must reach the mutating section; got {intervals}"

    first, second = sorted(intervals, key=lambda iv: iv[0])
    assert first[1] <= second[0], (
        "the two mutating sections overlapped — the upgrade is not serialised. "
        f"first={first}, second={second}"
    )
    assert results.get("a") == 0 and results.get("b") == 0, (
        f"both runs must succeed; got {results}"
    )
