# URN: test:migrate-projection-authority:plan-migration-rollout:P001-UNIT-002-irreversible-steps-carry-a-rollback
# Acceptance: acc:migrate-projection-authority:P001-UNIT-002-irreversible-steps-carry-a-rollback
# WMBT: wmbt:migrate-projection-authority:P001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: Every irreversible step in the authored rollout plan names a rollback TRIGGER and an exact RESTORE procedure, and no irreversible step is scheduled before a step it depends on — and every repo the plan touches has agreed before the first one-way door. Refs #1434.
"""Every one-way door carries a rollback (P001-UNIT-002).

wagon: migrate-projection-authority | feature: plan-migration-rollout | phase: GREEN
WMBT: wmbt:migrate-projection-authority:P001

A step whose rollback is "revert the commit" has not been thought about. Reverting the commit that
deleted the manifest readers does not restore the manifest — which has been going stale for as long
as the readers were gone — so the restored readers would read a lie. A rollback entry is only worth
the paper it is on if it names **what will tell you it went wrong** and **what exactly you type**.

Both one-way doors in this plan are checked for both halves; the dependency order is checked because
it is the reason the graph is written down at all; and the cross-repo sign-off is checked because a
one-way door opened by one repo, on behalf of two, is an outage with a commit message.
Refs #1434 / #1400.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.state.rollout import (
    RULE_AGREED_BEFORE_IRREVERSIBLE,
    RULE_IRREVERSIBLE_AFTER_DEPENDENCY,
    RULE_IRREVERSIBLE_HAS_ROLLBACK,
    check,
    load_plan,
)

REPO = Path(__file__).resolve().parents[5]
_PLAN = REPO / ".atdd" / "policy" / "migration-rollout.yaml"


def test_p001_unit_002_irreversible_steps_carry_a_rollback(tmp_path) -> None:
    """Each irreversible step names a trigger and a restore; none jumps its dependency."""
    assert check(REPO).ok, check(REPO).render()
    plan = load_plan(_PLAN)

    irreversible = [step for step in plan.ordered if step.irreversible]
    assert irreversible, "a migration with no one-way door has not been modelled honestly"

    for step in irreversible:
        assert step.rollback is not None, f"{step.id} is irreversible and names no rollback"
        assert step.rollback.complete, f"{step.id}'s rollback is incomplete"
        # Not a slogan: a trigger says what you will OBSERVE, a restore says what you will DO.
        assert len(step.rollback.trigger.split()) >= 5, step.id
        assert len(step.rollback.restore.split()) >= 5, step.id

    # No irreversible step is scheduled before a step it depends on.
    order = {step.id: step.order for step in plan.ordered}
    for step in irreversible:
        for dep in step.depends_on:
            assert order[dep] < step.order, f"{step.id} runs before its dependency {dep}"

    # Every repo the plan touches has agreed BEFORE the first one-way door.
    assert set(plan.repos) <= set(plan.agreed_by), plan.repos

    # The check BITES on each of the three.
    document = yaml.safe_load(_PLAN.read_text(encoding="utf-8"))

    # (a) an irreversible step whose rollback names a trigger but no restore procedure.
    doc_a = yaml.safe_load(yaml.safe_dump(document))
    for step in doc_a["steps"]:
        if step["id"] == "decommission-manifest":
            step["rollback"]["restore"] = ""
    path_a = tmp_path / "no-restore.yaml"
    path_a.write_text(yaml.safe_dump(doc_a, sort_keys=False), encoding="utf-8")
    problems = check(REPO, plan_path=path_a).problems
    assert any(p.rule == RULE_IRREVERSIBLE_HAS_ROLLBACK and "restore" in p.detail for p in problems)

    # (b) an irreversible step scheduled before what it depends on.
    doc_b = yaml.safe_load(yaml.safe_dump(document))
    for step in doc_b["steps"]:
        if step["id"] == "decommission-manifest":
            step["order"] = 35   # ahead of remove-github-hot-path (40), which it depends on
    path_b = tmp_path / "jumps-dep.yaml"
    path_b.write_text(yaml.safe_dump(doc_b, sort_keys=False), encoding="utf-8")
    assert any(p.rule == RULE_IRREVERSIBLE_AFTER_DEPENDENCY
               for p in check(REPO, plan_path=path_b).problems)

    # (c) a one-way door opened before the other repo agreed.
    doc_c = yaml.safe_load(yaml.safe_dump(document))
    doc_c["agreed_by"].pop("github-extension")
    path_c = tmp_path / "unagreed.yaml"
    path_c.write_text(yaml.safe_dump(doc_c, sort_keys=False), encoding="utf-8")
    problems = check(REPO, plan_path=path_c).problems
    assert any(p.rule == RULE_AGREED_BEFORE_IRREVERSIBLE for p in problems)
    assert any("github-extension" in p.detail for p in problems)
