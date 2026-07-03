# URN: test:author-plan-substrate:author-contract:E008-UNIT-003-build-author-fn-dispatches-contract
# Acceptance: acc:author-plan-substrate:E008-UNIT-003-build-author-fn-dispatches-contract
# WMBT: wmbt:author-plan-substrate:E008
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E008-UNIT-003 (plan contract) — the plan Confirm->author seam dispatches a
locked unit of kind `contract` to create_contract, like every other plan unit
kind. Without the seam wired, kind `contract` raises the no-writer error.

RED until build_author_fn learns the `contract` kind (#1314 B).
"""
from __future__ import annotations

from pathlib import Path

from atdd.planner.commands.plan_session import build_author_fn


def test_build_author_fn_dispatches_contract_kind(tmp_path):
    author_fn = build_author_fn(tmp_path)
    spec = {"identity": "commons:coach:probe-card", "title": "ProbeCard"}

    out = author_fn("contract", spec)

    out = Path(out)
    assert out == tmp_path / "contracts" / "commons" / "coach" / "probe-card.schema.json"
    assert out.exists()
