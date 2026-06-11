# URN: test:mediate-worker-decisions:surface-worker-decisions:Y002-SMOKE-001-live-worker-launch-argv-matches-policy
# Acceptance: acc:mediate-worker-decisions:Y002-SMOKE-001-live-worker-launch-argv-matches-policy
# WMBT: wmbt:mediate-worker-decisions:Y002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""Y002-SMOKE-001 — a live worker's launch argv is the image of the policy.

Live end-to-end: the captured launch argv of a toolkit-spawned worker contains the
policy's auto_allow tools in --allowedTools and does NOT pre-authorize the broad Bash
class (bare ``Bash`` / ``Bash(*)`` / ``Bash(:*)``) nor any forbidden bypass flag;
scoped ``Bash(<cmd>:*)`` safe prefixes MAY appear (the config-driven freedom set,
E031 #1062). The harness is real; runs at the SMOKE phase after GREEN.
"""
from __future__ import annotations

import re

import pytest

from atdd.mediate_worker_decisions.surface_worker_decisions.live_smoke import (
    launch_argv_matches_policy_live_smoke,
    live_smoke_available,
)

# Bare ``Bash`` not followed by a scoping '(' — the over-broad form that must surface.
_BARE_BASH_RE = re.compile(r"Bash(?!\()")


def test_y002_smoke_001_live_worker_launch_argv_matches_policy():
    # Live-on-demand: skips cleanly in CI / when not opted in (ATDD_LIVE_SMOKE=1).
    # Documented run: docs/smoke-audit.md (#971).
    skip = live_smoke_available()
    if skip:
        pytest.skip(skip)
    evidence = launch_argv_matches_policy_live_smoke()
    assert evidence["surfaced"] is True
    after_allowed = evidence["launch_command"].partition("--allowedTools")[2]
    # Bare / over-broad Bash must never be pre-authorized; scoped Bash(<cmd>:*) may.
    assert not _BARE_BASH_RE.search(after_allowed), evidence["launch_command"]
    assert "Bash(*)" not in after_allowed and "Bash(:*)" not in after_allowed
