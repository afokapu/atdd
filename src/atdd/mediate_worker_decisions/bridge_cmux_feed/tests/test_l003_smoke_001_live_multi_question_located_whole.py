# URN: test:mediate-worker-decisions:bridge-cmux-feed:L003-SMOKE-001-live-multi-question-located-whole
# Acceptance: acc:mediate-worker-decisions:L003-SMOKE-001-live-multi-question-located-whole
# WMBT: wmbt:mediate-worker-decisions:L003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""L003-SMOKE-001 — a real multi-question item is located as a whole block document.

Drives the REAL bridge against a live cmux workspace: a worker blocked on a
three-question AskUserQuestion is located from the Feed and mapped to a document
carrying one block per question (not flattened to the first). Runs wherever cmux
is on PATH; skips otherwise.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_l003_smoke_001_live_multi_question_located_whole():
    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
        multi_question_unblock_live_smoke,
    )

    evidence = multi_question_unblock_live_smoke()

    # every question located as its own block — not flattened to the first
    assert evidence["questions_located"] >= 3
