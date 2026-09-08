# URN: test:govern-providers:E004-SMOKE-001-real-lock-narrows-to-one-selected-rule
# Acceptance: acc:govern-providers:E004-SMOKE-001-real-lock-narrows-to-one-selected-rule
# WMBT: wmbt:govern-providers:E004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E004-SMOKE-001 — against the toolkit's REAL committed binding.lock.yaml, selecting
one bound rule resolves to exactly that rule while the unselected resolution carries the
whole set. This is the claim the pre-write gate rests on, proven on real data rather
than a fixture: without narrowing, one artifact write costs one provider subprocess per
bound convention.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.runner import _bound_conventions, resolve_substrate_home

_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_e004_smoke_001_real_lock_narrows_to_one_selected_rule():
    home = resolve_substrate_home(_REPO_ROOT)
    every = _bound_conventions(home)

    # The real lock binds many rules — that is precisely the cost being avoided.
    assert len(every) > 1, "real lock binds <=1 convention; narrowing proves nothing here"

    picked = str(every[0]["convention_id"])
    selected = _bound_conventions(home, rules={picked})

    assert [str(c["convention_id"]) for c in selected] == [picked]
    assert len(selected) < len(every)
