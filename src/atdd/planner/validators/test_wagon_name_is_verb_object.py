# URN: component:atdd-plan-core:naming:WagonNameIsVerbObject:backend:tests
# Acceptance: acc:define-plans:C003-SMOKE-001-wagon-verb-object-blocks-at-confirm
# Acceptance: acc:define-plans:C003-SMOKE-002-cli-exit-nonzero-on-naming-refusal
# Acceptance: acc:define-plans:E002-SMOKE-001-naming-rules-bound-and-run
# WMBT: wmbt:define-plans:C003
# Phase: SMOKE
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

import json

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


def _drive_cli_to_confirm(tmp_path, slug: str) -> int:
    """Drive the real ``atdd plan`` CLI dispatch (``plan_session_cli.run``) from
    start through confirm with one kept wagon ``slug``, returning confirm's exit
    code. Pins the exit-code contract end-to-end through the shared gate-refusal
    path so a future refactor cannot silently regress a refused confirm to 0."""
    from atdd.planner.commands.plan_session_cli import run

    root = str(tmp_path)
    spec = json.dumps({"wagon": slug})
    assert run(["--root", root, "start", "--id", "c1",
                "--main-job", "mj", "--issue", "demo-slug"]) == 0
    assert run(["--root", root, "source", "--id", "c1", "req"]) == 0
    assert run(["--root", root, "advance", "--id", "c1", "--step", "locate"]) == 0
    assert run(["--root", root, "advance", "--id", "c1", "--step", "prepare"]) == 0
    assert run(["--root", root, "unit", "--id", "c1", "--kind", "wagon",
                "--ref", f"wagon:{slug}", "--spec", spec]) == 0
    assert run(["--root", root, "decide", "--id", "c1",
                "--ref", f"wagon:{slug}", "--verdict", "keep"]) == 0
    assert run(["--root", root, "advance", "--id", "c1", "--step", "confirm"]) == 0
    return run(["--root", root, "confirm", "--id", "c1"])


def test_confirm_cli_exits_nonzero_on_naming_refusal(tmp_path) -> None:
    """`atdd plan confirm` must exit non-zero when the verb-object gate refuses a
    kept wagon name, and 0 when the name is verb-object (#1276)."""
    assert _drive_cli_to_confirm(tmp_path / "bad", "mode-select") != 0
    assert _drive_cli_to_confirm(tmp_path / "good", "manage-users") == 0
