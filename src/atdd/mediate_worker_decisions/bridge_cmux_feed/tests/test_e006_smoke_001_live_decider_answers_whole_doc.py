# URN: test:mediate-worker-decisions:bridge-cmux-feed:E006-SMOKE-001-live-decider-answers-whole-doc
# Acceptance: acc:mediate-worker-decisions:E006-SMOKE-001-live-decider-answers-whole-doc
# WMBT: wmbt:mediate-worker-decisions:E006
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E006-SMOKE-001 — the real claude -p decider answers every block of a live doc.

Drives the REAL LlmCoach (claude -p) over a live three-question document: the
verdict must carry a non-empty answer for every block (not just the first).
Runs wherever cmux is on PATH; skips otherwise.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_e006_smoke_001_live_decider_answers_whole_doc():
    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
        multi_question_unblock_live_smoke,
    )

    evidence = multi_question_unblock_live_smoke()

    # the decider answered every block of the document, not only the first
    assert evidence["blocks_answered"] == evidence["questions_located"]
    assert evidence["blocks_answered"] >= 3
