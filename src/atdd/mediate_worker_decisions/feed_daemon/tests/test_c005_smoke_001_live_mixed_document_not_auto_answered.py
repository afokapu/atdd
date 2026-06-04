# URN: test:mediate-worker-decisions:feed-daemon:C005-SMOKE-001-live-mixed-document-not-auto-answered
# Acceptance: acc:mediate-worker-decisions:C005-SMOKE-001-live-mixed-document-not-auto-answered
# WMBT: wmbt:mediate-worker-decisions:C005
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C005-SMOKE-001 — a live mixed document with a dangerous block is escalated.

A real document composing a dangerous block with safe blocks must be escalated
(document-atomic), never auto-answered. Not inducible in this environment: cmux
AskUserQuestion sub-questions are choice-only (no dangerous confirm block in a
question item), and a standalone dangerous permission does not block the Feed
under cmux auto-mode (PermissionNotInducible) — the same condition that hard-skips
C003/C004 live. The hermetic C005 unit+integration tests carry the
document-atomic safety guarantee in the meantime.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="mixed document with a dangerous block not inducible live (cmux "
    "questions are choice-only; dangerous permissions don't block under cmux "
    "auto-mode) — hermetic C005 unit+integration carry the guarantee"
)


def test_c005_smoke_001_live_mixed_document_not_auto_answered():
    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
        danger_live_smoke,
    )

    evidence = danger_live_smoke()
    assert evidence["auto_replied"] is False
