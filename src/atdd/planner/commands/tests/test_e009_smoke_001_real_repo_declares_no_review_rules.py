# URN: test:author-atdd-substrate:E009-SMOKE-001-real-repo-declares-no-review-rules
# Acceptance: acc:author-atdd-substrate:E009-SMOKE-001-real-repo-declares-no-review-rules
# WMBT: wmbt:author-atdd-substrate:E009
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E009-SMOKE-001 — the toolkit's OWN committed .atdd/config.yaml declares no
author_review rules, so the real authoring path resolves an empty rule set and stays
unguarded.

This is the agnosticism claim measured against reality rather than a fixture: shipping
the seam must cost an install with no review extension nothing. If this test ever goes
red because the toolkit opted itself in, that is a deliberate decision that should be
made explicitly, not discovered.
"""
from __future__ import annotations

from pathlib import Path

from atdd.planner.commands.author import _declared_review_rules

_REPO_ROOT = Path(__file__).resolve().parents[5]


def test_e009_smoke_001_real_repo_declares_no_review_rules():
    assert (_REPO_ROOT / ".atdd").is_dir(), "expected the real control surface at the repo root"

    assert _declared_review_rules(_REPO_ROOT / "plan" / "probe.yaml") == []
