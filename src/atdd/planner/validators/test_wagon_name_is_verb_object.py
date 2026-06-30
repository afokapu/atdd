# URN: component:atdd-plan-core:naming:WagonNameIsVerbObject:backend:tests
# Runtime: python
# Purpose: Foundational wagon naming (verb-object) is validator-backed and blocks at Confirm (#1276).
"""Validators for ``planner.wagon.name-is-verb-object`` (#1276).

Foundational planner naming was prose-only "preference"; #1276 promotes it to a
bound, confirm-blocking rule. These tests pin:

* the rule is registered (``bind_rule`` resolves it),
* the pragmatic verb-object mechanic — kebab-case, >=2 tokens, leading token in the
  convention verb lexicon, no connective tokens — accepts good names and rejects
  the real-world bad names from the issue (``mode-select``, ``blitz``,
  ``respond-and-preview``, ``route-to-mode``), and
* ``PlanSession.confirm`` refuses to lock a kept wagon unit whose slug violates the
  rule, while a verb-object slug locks normally (the missing enforcement teeth).
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.rule_binding import bind_rule
from atdd.planner.naming import is_verb_object
from atdd.planner.commands.plan_session import (
    PlanSession, SessionGateError, Step, Unit, Verdict,
)

# Good verb-object slugs — incl. the convention's own canonical examples.
GOOD = [
    "resolve-dilemmas", "commit-state", "manage-users",
    "track-timebank", "make-choice", "configure-match",
]

# Real failures observed driving `atdd plan` (issue #1276 motivation).
BAD = ["mode-select", "blitz", "respond-and-preview", "route-to-mode"]


def test_rule_is_bound() -> None:
    rule = bind_rule("planner.wagon.name-is-verb-object")
    assert rule.rule_id == "planner.wagon.name-is-verb-object"


@pytest.mark.parametrize("slug", GOOD)
def test_good_wagon_names_pass(slug: str) -> None:
    ok, reason = is_verb_object(slug, artifact="wagon")
    assert ok, f"{slug!r} should be verb-object but failed: {reason}"


@pytest.mark.parametrize("slug", BAD)
def test_bad_wagon_names_fail(slug: str) -> None:
    ok, reason = is_verb_object(slug, artifact="wagon")
    assert not ok, f"{slug!r} should violate verb-object but passed"
    assert reason, "a violation must carry a human-readable reason"


def _confirm_session_with_wagon(slug: str) -> PlanSession:
    s = PlanSession(session_id="w1")
    s.step = Step.CONFIRM.value
    s.issue_ref = "demo-slug"
    s.add_unit(Unit(kind="wagon", ref=f"wagon:{slug}",
                    verdict=Verdict.KEEP.value, spec={"wagon": slug}))
    return s


def test_confirm_blocks_non_verb_object_wagon(tmp_path) -> None:
    s = _confirm_session_with_wagon("mode-select")
    with pytest.raises(SessionGateError):
        s.confirm(root=tmp_path)
    assert s.locked is False


def test_confirm_locks_verb_object_wagon(tmp_path) -> None:
    s = _confirm_session_with_wagon("manage-users")
    s.confirm(root=tmp_path)
    assert s.locked is True
