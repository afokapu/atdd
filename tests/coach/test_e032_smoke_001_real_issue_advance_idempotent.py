# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:E032-SMOKE-001-real-issue-advance-idempotent
# Acceptance: acc:spawn-agents:E032-SMOKE-001-real-issue-advance-idempotent
# WMBT: wmbt:spawn-agents:E032
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E032-SMOKE-001 — against a real GitHub issue the advance is idempotent: the
first call lands the target label and a second call changes nothing.

Live-on-demand against the real ``gh`` label API. Skips in CI / when not opted
in (ATDD_RUN_SMOKE=1). In RED the live-smoke harness is unimplemented → skipped.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("ATDD_RUN_SMOKE") != "1",
        reason="live gh label idempotency smoke — opt in with ATDD_RUN_SMOKE=1",
    ),
]


def test_real_issue_advance_idempotent():
    from atdd.coach.label_advance.live_smoke import (  # noqa: WPS433
        advance_idempotent_live_smoke,
    )

    evidence = advance_idempotent_live_smoke()

    assert evidence["after_first_label"] == evidence["target_label"], (
        "first call must land exactly the target atdd:<phase> label"
    )
    assert evidence["second_call_mutated"] is False, "the second call must change nothing"
    assert evidence["errored"] is False, "neither call errors"
