# URN: test:mediate-worker-decisions:bridge-cmux-feed:E007-SMOKE-001-live-multi-question-all-answered
# Acceptance: acc:mediate-worker-decisions:E007-SMOKE-001-live-multi-question-all-answered
# WMBT: wmbt:mediate-worker-decisions:E007
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E007-SMOKE-001 — the live multi-question + checkbox case auto-answers ALL of it.

The headline #976 proof. Drives the REAL bridge against a live cmux workspace
whose worker blocks on ONE AskUserQuestion carrying three questions (single +
single + multi-select checkbox). The real runner (LlmCoach over claude -p +
CmuxFeedTransport) replies with a flat selections list covering EVERY question —
checkbox included — and the whole item resolves, no human in the TUI. Runs
wherever cmux is on PATH; skips otherwise.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_e007_smoke_001_live_multi_question_all_answered():
    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
        multi_question_unblock_live_smoke,
    )

    evidence = multi_question_unblock_live_smoke()

    # the whole multi-question resolved (worker proceeds) ...
    assert evidence["resolved"] is True
    # ... and the flat reply carried selections for MORE than the first question
    # (the live bug delivered only one) — including the checkbox's labels.
    assert len(evidence["selections"]) >= 3
