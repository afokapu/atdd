# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C019-SMOKE-001-a-non-atdd-repo-exercises-the-surface-with-no-layout-override
# Acceptance: acc:govern-lifecycle:C019-SMOKE-001-a-non-atdd-repo-exercises-the-surface-with-no-layout-override
# WMBT: wmbt:govern-lifecycle:C019
# Phase: SMOKE
# Layer: integration
# Smoke: true
# Assertion: behavioral
# Purpose: atdd cannot be its own witness here (#1618) — a real non-atdd repo drives the surface end to end, and leans on no repo-specific layout override
"""C019-SMOKE-001 — the witness that is not atdd.

#1618 ruled that atdd is the route-control LIBRARY and not a Station Master: it
has no ``TrainRunner``, no application entrypoint and no dispatcher for the
declared action names, so wiring a JOURNEY_MAP into ``src/atdd/**`` would be "a
dead route table" satisfying the letter of ``declaration_to_station`` while
leaving the remaining binding directions vacuously true. That ruling is what
makes this acceptance load-bearing rather than a nicety: **the Station Master
lives in the CONSUMER**, so the consumer is the only place the surface can be
witnessed working.

TWO WAYS THIS COULD PASS WITHOUT PROVING ANYTHING, both closed below:

1. *Passing because it ran inside atdd.* The fixture is a real repository on
   disk with its own git repo, its own ``.atdd/`` control root, its own package
   name, its own ``plan/_trains.yaml`` and its own interlocking YAML — action
   names and idiom belonging to it, not to atdd.

2. *Passing because of a layout override.* ``.atdd/config.yaml ::
   interlocking_layout`` already points the detector at
   ``src/atdd/runtime/interlocking/*.py`` instead of the game-app default, and
   #1598 names that as the shape to avoid — a check that works only where it was
   written. The fixture therefore adopts the detector's DEFAULT layout
   (``python/trains/**/*.py`` + ``python/app.py``) and carries NO such key.
   ``test_no_answer_depends_on_the_repos_config`` runs with the file ABSENT, so
   this is asserted rather than asserted-by-convention.

atdd needs that override because atdd is the OUTLIER, not because the check is
layout-bound. The shape used here is already proven in-tree by the passing
``bilateral_binding_complete`` fixture in the train-interlocking-enforcement
extension — which is also, today, parsed with ``ast`` and never executed, making
it a live instance of this test's FAIL leg.

THE FAIL LEG IS THE DISCRIMINATOR. Without it, an implementation that answered
PASS unconditionally would satisfy every other assertion here. The same repo and
the same registration must yield a DIFFERENT answer based only on whether a
dispatch actually happened.

RED state: the registration surface, the attestation and the gate do not exist.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.decision import GateContext, GateVerdict

pytestmark = [pytest.mark.platform]

_ISSUE = 999119


def _ctx(worktree: Path) -> GateContext:
    return GateContext(
        issue_number=_ISSUE, from_phase="SMOKE", to_phase="REFACTOR", worktree=worktree
    )


@pytest.fixture
def consumer_repo(tmp_path: Path):
    """A real non-atdd repository on disk, at the detector's DEFAULT layout."""
    from atdd.coach.gate.tests._c019_support import build_consumer_repo

    return build_consumer_repo(tmp_path)


def test_after_a_real_dispatch_the_gate_confirms_instantiation(consumer_repo):
    """C019-SMOKE-001: PASS, naming the consumer's own train."""
    from atdd.coach.gate.train_instantiation_check import TrainInstantiationGateCheck

    consumer_repo.station_master_dispatch(action="start_match")
    result = TrainInstantiationGateCheck().run(_ctx(consumer_repo.root))

    assert result.verdict is GateVerdict.PASS
    assert consumer_repo.train_id in result.message, (
        "the answer must name the train the dispatch routed to — and it is the "
        "CONSUMER's train id, which appears nowhere in atdd's own plan"
    )


def test_before_any_dispatch_the_same_repo_answers_declared_but_not_instantiated(
    consumer_repo,
):
    """C019-SMOKE-001: FAIL — a JOURNEY_MAP literal moves nothing.

    Same repo, same registration, no dispatch. This is the dead route table
    #1618 refused to create, and the state the extension's own passing fixture
    is in right now: statically bound, dynamically inert.
    """
    from atdd.coach.gate.train_instantiation_check import TrainInstantiationGateCheck

    assert consumer_repo.journey_map_is_declared(), (
        "precondition: the map IS declared — this leg proves declaration alone "
        "does not satisfy the gate"
    )
    result = TrainInstantiationGateCheck().run(_ctx(consumer_repo.root))

    assert result.verdict is GateVerdict.FAIL
    assert result.passed is False


def test_an_unresolvable_registration_target_answers_could_not_confirm(consumer_repo):
    """C019-SMOKE-001: COULD_NOT_CHECK, naming the target."""
    from atdd.coach.gate.train_instantiation_check import TrainInstantiationGateCheck

    consumer_repo.point_registration_at("consumer_app.nonexistent:JOURNEY_MAP")
    result = TrainInstantiationGateCheck().run(_ctx(consumer_repo.root))

    assert result.verdict is GateVerdict.COULD_NOT_CHECK
    assert "consumer_app.nonexistent" in result.message


def test_no_answer_depends_on_the_repos_config(consumer_repo):
    """C019-SMOKE-001: the no-override assertion, run with the file ABSENT.

    A check that works only where it was written is the failure being avoided,
    not a limitation being accepted. If any of the three answers moves when
    ``.atdd/config.yaml`` disappears, the gate is reading a repo-specific escape
    hatch and this whole acceptance is decorative.
    """
    from atdd.coach.gate.train_instantiation_check import TrainInstantiationGateCheck

    check = TrainInstantiationGateCheck()
    assert not consumer_repo.has_interlocking_layout_key(), (
        "the fixture must never carry interlocking_layout — it adopts the "
        "detector's DEFAULT layout instead"
    )

    before = check.run(_ctx(consumer_repo.root)).verdict
    consumer_repo.station_master_dispatch(action="start_match")
    after = check.run(_ctx(consumer_repo.root)).verdict

    with consumer_repo.without_config_yaml():
        assert check.run(_ctx(consumer_repo.root)).verdict is after
        consumer_repo.reset_dispatches()
        assert check.run(_ctx(consumer_repo.root)).verdict is before

    assert before is GateVerdict.FAIL and after is GateVerdict.PASS, (
        "the two answers must actually differ, or the config-independence "
        "assertion above is comparing a constant to itself"
    )


def test_the_run_never_touches_the_atdd_repos_own_control_root(consumer_repo):
    """C019-SMOKE-001: no live control root, no live issue, no cross-repo bleed."""
    from atdd.coach.gate.train_instantiation_check import TrainInstantiationGateCheck
    from atdd.coach.gate.tests._c019_support import recording_path_access

    with recording_path_access() as touched:
        consumer_repo.station_master_dispatch(action="start_match")
        TrainInstantiationGateCheck().run(_ctx(consumer_repo.root))

    strayed = [p for p in touched if not str(p).startswith(str(consumer_repo.root))]
    assert strayed == [], (
        f"the run touched paths outside the fixture repo: {strayed[:5]}"
    )
