# URN: test:define-plans:atdd-plan-session:Y002-UNIT-006-frozen-artifacts-and-rule-ids-still-resolve
# Acceptance: acc:define-plans:Y002-UNIT-006-frozen-artifacts-and-rule-ids-still-resolve
# WMBT: wmbt:define-plans:Y002
# Phase: RED
# Layer: unit
# Assertion: structural
"""Y002-UNIT-006 — the frozen artifact filenames and rule IDs survive the rename.

Two things share the retired words and must not move with them:

1. Every WMBT artifact under plan/ is named by its step LETTER (D001, C006,
   Y002). The letter is the file's identity, so renaming the job steps to chase
   the new stage names would rename hundreds of files for no operator-visible
   benefit.
2. Three rule IDs carry `confirm` and are bound at import time under
   SPEC-COACH-RULEID-0007. The issue states this rename "changes no rule".

The phrase `confirm-before-author` therefore survives as a RULE name while the
STAGE it guards is now called Ratify. Both are true at once; this test pins the
first half so nobody "fixes" the inconsistency.

Tripwire: passes before and after, fails only on over-reach.
"""
from __future__ import annotations

import re

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule

REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"

WMBT_FILENAME = re.compile(r"^[DLPCEMYRK][0-9]{3}\.yaml$")

FROZEN_RULE_IDS = [
    "planner.plan.confirm-before-author",
    "planner.plan.confirm-binds-an-issue",
    "planner.plan.confirm-requires-interlocking-sanity",
]


def _wmbt_artifacts() -> list:
    return sorted(p for p in PLAN_DIR.rglob("*.yaml") if WMBT_FILENAME.match(p.name))


def test_the_plan_tree_still_holds_step_lettered_wmbt_artifacts():
    """A guard against the guard: if the glob silently matched nothing, every
    other assertion here would pass vacuously."""
    assert len(_wmbt_artifacts()) > 100


def test_every_step_lettered_wmbt_filename_still_resolves():
    unreadable = [str(p.relative_to(REPO_ROOT))
                  for p in _wmbt_artifacts() if not p.is_file()]
    assert not unreadable, f"WMBT artifacts no longer resolve: {unreadable}"


def test_no_wmbt_artifact_was_renamed_to_a_session_stage_letter():
    """Intent/Attach/Compose/Ratify have no WMBT letters. The resulting mnemonic
    mismatch with D001/L001/P001/C00x is accepted, not fixed."""
    for name in ("I001.yaml", "A001.yaml", "T001.yaml"):
        assert not list(PLAN_DIR.rglob(name)), f"unexpected new-stage artifact {name}"


@pytest.mark.parametrize("rule_id", FROZEN_RULE_IDS)
def test_each_confirm_named_rule_id_still_binds(rule_id):
    rule = bind_rule(rule_id)
    assert rule is not None


def test_the_confirm_before_author_rule_keeps_its_name():
    """The rule name outlives the stage name it was drawn from."""
    assert bind_rule("planner.plan.confirm-before-author") is not None
