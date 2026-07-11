# URN: test:migrate-projection-authority:plan-migration-rollout:P001-UNIT-001-plan-orders-shadow-before-blocking
# Acceptance: acc:migrate-projection-authority:P001-UNIT-001-plan-orders-shadow-before-blocking
# WMBT: wmbt:migrate-projection-authority:P001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The authored rollout plan schedules shadow-mode CI STRICTLY BEFORE both the GitHub hot-path removal and the manifest fallback removal — and the check bites when a plan reorders them, or omits the shadow step altogether. Refs #1434.
"""Shadow mode is staged ahead of every blocking step (P001-UNIT-001).

wagon: migrate-projection-authority | feature: plan-migration-rollout | phase: RED
WMBT: wmbt:migrate-projection-authority:P001

This is the single most important ordering constraint in the wagon, and it is the one a schedule
under pressure will quietly violate. You do not get to delete the fallback and *then* find out
whether the thing replacing it agrees with it. Shadow mode is what buys the evidence that every
later step spends; a plan that spends it first has not sequenced a migration, it has sequenced a
hope. Refs #1434 / #1400.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.state.rollout import (
    MODE_BLOCKING,
    MODE_SHADOW,
    RULE_SHADOW_BEFORE_BLOCKING,
    check,
    load_plan,
)

REPO = Path(__file__).resolve().parents[5]
_PLAN = REPO / ".atdd" / "policy" / "migration-rollout.yaml"


def test_p001_unit_001_plan_orders_shadow_before_blocking(tmp_path) -> None:
    """Shadow-mode CI precedes both the hot-path removal and the manifest-fallback removal."""
    report = check(REPO)
    assert report.ok, report.render()

    plan = load_plan(_PLAN)
    order = {step.id: step.order for step in plan.ordered}

    # The two removals the acceptance names, both after the shadow step.
    shadow_order = order["shadow-ci"]
    assert order["remove-github-hot-path"] > shadow_order
    assert order["decommission-manifest"] > shadow_order

    # And not merely those two: EVERY blocking step and EVERY irreversible one is behind it.
    for step in plan.ordered:
        if step.mode == MODE_BLOCKING or step.irreversible:
            assert step.order > shadow_order, f"{step.id} is scheduled at or before shadow mode"

    # The check BITES. Reorder the plan so the hot-path removal jumps the shadow step...
    document = yaml.safe_load(_PLAN.read_text(encoding="utf-8"))
    for step in document["steps"]:
        if step["id"] == "remove-github-hot-path":
            step["order"] = 5   # ahead of shadow-ci
    reordered = tmp_path / "reordered.yaml"
    reordered.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    broken = check(REPO, plan_path=reordered)
    assert not broken.ok
    problems = [p for p in broken.problems if p.rule == RULE_SHADOW_BEFORE_BLOCKING]
    assert problems and problems[0].step == "remove-github-hot-path"

    # ...and a plan with NO shadow step at all is refused outright: turning blocking mode on with
    # no evidence is the failure this rule exists to prevent, not an edge case of it.
    document = yaml.safe_load(_PLAN.read_text(encoding="utf-8"))
    document["steps"] = [s for s in document["steps"] if s["mode"] != MODE_SHADOW]
    none = tmp_path / "no-shadow.yaml"
    none.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    assert any(p.rule == RULE_SHADOW_BEFORE_BLOCKING for p in check(REPO, plan_path=none).problems)
