# URN: test:observe-and-correct:observer-runtime-and-rules:M003-UNIT-004-rule-16-smoke-skip
# Acceptance: acc:observe-and-correct:M003-UNIT-004-rule-16-smoke-skip
# WMBT: wmbt:observe-and-correct:M003
# Phase: RED
# Layer: application
"""M003-UNIT-004 — Rule `coach.observer.smoke-skip` (rule 16).

Per spec §0.2 / §8.3, the rule absorbs the ``--status REFACTOR`` clause
of ``babysit.detect_violation`` into the observer substrate. The rule
must:

  * fire when the agent transitions GREEN → REFACTOR with no intervening
    SMOKE
  * NOT fire when the trajectory is GREEN → SMOKE → REFACTOR
  * be at parity with babysit's ``detect_violation`` SMOKE-skip clause
    for the same screen patterns

Issue #513 (L4). Spec: ``atdd-coach-spec-v9.md`` §6.4 (phase-ordering),
§8.3 (rule table).
"""
from __future__ import annotations

import pytest

from atdd.coach.commands import babysit, observer

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_rule_16_module_exposes_build_rule_and_predicate():
    from atdd.coach.observer_rules import smoke_skip

    assert callable(smoke_skip.build_rule)
    assert callable(smoke_skip.predicate)
    # Absorbed verbatim per spec §0.2:
    assert smoke_skip.detect_violation is babysit.detect_violation


def test_rule_16_build_rule_binds_canonical_rule_id():
    from atdd.coach.observer_rules import smoke_skip

    rule = smoke_skip.build_rule()
    assert isinstance(rule, observer.ObserverRule)
    assert rule.rule_id == "coach.observer.smoke-skip"


# ---------------------------------------------------------------------------
# Parity with babysit.detect_violation SMOKE-skip clause
# ---------------------------------------------------------------------------


def test_rule_16_fires_on_refactor_status_without_smoke_in_screen():
    """``--status REFACTOR`` with no SMOKE token in the visible screen fires."""
    from atdd.coach.observer_rules import smoke_skip

    screen = "agent ran: atdd issue 513 --status REFACTOR\n"

    # Babysit baseline: this is the SMOKE-skip violation pattern.
    baseline = babysit.detect_violation(screen)
    assert baseline is not None
    assert baseline.matched == "SMOKE skip"

    ctx = observer.ObservedInput(
        agent_id="agent-A",
        log_lines=tuple(screen.splitlines()),
    )
    assert smoke_skip.predicate(ctx) is True


def test_rule_16_silent_on_green_smoke_refactor_trajectory():
    """A trajectory GREEN → SMOKE → REFACTOR (with SMOKE visible) does NOT fire."""
    from atdd.coach.observer_rules import smoke_skip

    screen = (
        "ran: atdd issue 513 --status SMOKE\n"
        "all SMOKE tests passed\n"
        "ran: atdd issue 513 --status REFACTOR\n"
    )

    # Babysit baseline: SMOKE token present, so detect_violation returns None.
    baseline = babysit.detect_violation(screen)
    assert baseline is None or baseline.matched != "SMOKE skip", (
        "babysit baseline: SMOKE present in screen → no SMOKE-skip violation"
    )

    ctx = observer.ObservedInput(
        agent_id="agent-A",
        log_lines=tuple(screen.splitlines()),
    )
    assert smoke_skip.predicate(ctx) is False


def test_rule_16_silent_on_other_screens():
    """Screens without ``--status REFACTOR`` never fire the SMOKE-skip rule."""
    from atdd.coach.observer_rules import smoke_skip

    for screen in (
        "",
        "just running tests\n",
        "ran: atdd issue 513 --status GREEN\n",
        "ran: atdd issue 513 --status SMOKE\n",
    ):
        ctx = observer.ObservedInput(
            agent_id="agent-A",
            log_lines=tuple(screen.splitlines()),
        )
        assert smoke_skip.predicate(ctx) is False, (
            f"rule 16 fired on screen with no REFACTOR transition: {screen!r}"
        )


def test_rule_16_does_not_fire_on_atdd_hand_edit_violation():
    """``detect_violation`` flags two distinct cases (.atdd/ hand-edit AND
    SMOKE-skip). Rule 16 owns ONLY the SMOKE-skip clause — the .atdd/
    hand-edit violation is a separate observer rule (out of scope here)."""
    from atdd.coach.observer_rules import smoke_skip

    screen = "ran: Edit .atdd/manifest.yaml\n"

    # Babysit baseline: this IS a violation, but it's the .atdd/ hand-edit
    # variant — not the SMOKE-skip variant rule 16 covers.
    baseline = babysit.detect_violation(screen)
    assert baseline is not None and baseline.matched == ".atdd/ hand-edit"

    ctx = observer.ObservedInput(
        agent_id="agent-A",
        log_lines=tuple(screen.splitlines()),
    )
    assert smoke_skip.predicate(ctx) is False
