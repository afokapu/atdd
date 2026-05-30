# URN: test:govern-lifecycle:freeze-coach-core-typed-api-and-phase-machine:E035-UNIT-001-pure-functions-importable-and-deterministic
# Acceptance: acc:govern-lifecycle:E035-UNIT-001-pure-functions-importable-and-deterministic
# WMBT: wmbt:govern-lifecycle:E035
# Phase: RED
# Layer: backend.application
"""AC-UNIT-001 — the five Coach-core pure policy functions are importable from
``atdd.coach.core`` and return the correct typed decision for a table of
hand-built ``(Evidence, Conventions)`` inputs, with no mocking and no I/O.

Coach decomposition Child 1 (docs/coach-decomposition.md §4.1–§4.3, §13.1).

RED state: ``atdd.coach.core`` and ``atdd.coach.core.types`` do not exist yet,
so every import below raises ``ModuleNotFoundError`` and the table tests fail.

This is the comprehensive, table-driven pure-function suite the spec refers to
as ``tests/coach/test_core_pure.py``; identity comes from the ``# URN`` header
above (filename convention V3).
"""
from __future__ import annotations

import pytest

from atdd.coach.core import (
    escalation_for,
    evaluate_evidence,
    merge_readiness,
    next_transition,
    review_phase_output,
)
from atdd.coach.core.types import (
    CiState,
    Conventions,
    Evidence,
    IssueType,
    MergeVerdict,
    Persona,
    Phase,
    PhaseSpec,
    PrState,
    RuleSpec,
    TransitionDecision,
    ValidatorReport,
    Verdict,
    VerdictKind,
)

pytestmark = pytest.mark.coach


# --------------------------------------------------------------------------- #
# In-memory fixtures — NO file reads in the test body (AC-UNIT-001).           #
# Mirrors §4.5 phase machine data exactly.                                     #
# --------------------------------------------------------------------------- #

_PHASE_MACHINE_DATA: dict[Phase, tuple[Persona | None, tuple[Phase, ...], str | None]] = {
    Phase.INIT: (Persona.PLANNER, (Phase.PLANNED, Phase.BLOCKED, Phase.OBSOLETE),
                 "atdd validate planner --local --skip-api"),
    Phase.PLANNED: (Persona.TESTER, (Phase.RED, Phase.BLOCKED, Phase.OBSOLETE), None),
    Phase.RED: (Persona.CODER, (Phase.GREEN, Phase.BLOCKED, Phase.OBSOLETE), None),
    Phase.GREEN: (Persona.TESTER, (Phase.SMOKE, Phase.BLOCKED, Phase.OBSOLETE), None),
    Phase.SMOKE: (Persona.CODER, (Phase.REFACTOR, Phase.BLOCKED, Phase.OBSOLETE), None),
    Phase.REFACTOR: (Persona.CODER, (Phase.COMPLETE, Phase.BLOCKED, Phase.OBSOLETE), None),
    Phase.COMPLETE: (None, (), None),
    Phase.BLOCKED: (None, (Phase.INIT, Phase.PLANNED, Phase.RED, Phase.GREEN,
                            Phase.SMOKE, Phase.REFACTOR, Phase.OBSOLETE), None),
    Phase.OBSOLETE: (None, (), None),
}

# The single forward (happy-path) successor for each phase — first transition
# target that is not BLOCKED/OBSOLETE.
_FORWARD = {
    Phase.INIT: Phase.PLANNED,
    Phase.PLANNED: Phase.RED,
    Phase.RED: Phase.GREEN,
    Phase.GREEN: Phase.SMOKE,
    Phase.SMOKE: Phase.REFACTOR,
    Phase.REFACTOR: Phase.COMPLETE,
}


def _build_conventions() -> Conventions:
    phase_machine = {
        phase: PhaseSpec(
            name=phase,
            agent=agent,
            transitions_to=transitions,
            pre_commit_gate=gate,
        )
        for phase, (agent, transitions, gate) in _PHASE_MACHINE_DATA.items()
    }
    rules = {
        "coach.core.example.block": RuleSpec(
            rule_id="coach.core.example.block",
            severity=4,
            disposition="block",
            fix_hint="address the blocking violation",
        ),
    }
    return Conventions(
        phase_machine=phase_machine,
        rules=rules,
        prompt_templates={},
        snapshot_hash="sha256:test-fixture",
        snapshot_paths=("phase_machine.convention.yaml",),
    )


def _evidence(phase: Phase, **overrides) -> Evidence:
    base = dict(
        issue_number=888,
        issue_type=IssueType.IMPLEMENTATION,
        current_phase=phase,
        train_id="0001-self-compliance-validate",
        branch="feat/freeze-coach-core-typed-api-and-phase-machine",
        wmbts=(),
        validator_reports=(),
        ci_state=CiState.SUCCESS,
        pr_state=None,
        last_commit_sha="0" * 40,
        artifacts_present=frozenset(),
        elapsed_in_phase_seconds=10,
        conventions_hash="sha256:test-fixture",
    )
    base.update(overrides)
    return Evidence(**base)


def _blocking_report() -> ValidatorReport:
    return ValidatorReport(
        validator_id="example_validator",
        rule_id="coach.core.example.block",
        severity=4,
        disposition="block",
        unsuppressed_count=2,
        location="src/foo.py:10",
        detail="example violation",
    )


# --------------------------------------------------------------------------- #
# next_transition                                                             #
# --------------------------------------------------------------------------- #

_ADVANCING_PHASES = [
    Phase.INIT, Phase.PLANNED, Phase.RED,
    Phase.GREEN, Phase.SMOKE, Phase.REFACTOR,
]


@pytest.mark.parametrize("phase", _ADVANCING_PHASES)
def test_next_transition_proceeds_to_forward_phase(phase: Phase):
    conv = _build_conventions()
    decision = next_transition(_evidence(phase), conv)

    assert isinstance(decision, TransitionDecision)
    assert decision.from_phase is phase
    assert decision.verdict.kind is VerdictKind.PROCEED
    assert decision.to_phase is _FORWARD[phase]


@pytest.mark.parametrize("phase", _ADVANCING_PHASES)
def test_next_transition_persona_matches_phase_machine_agent(phase: Phase):
    """I-5: the dispatched persona is the phase_machine agent for the current phase."""
    conv = _build_conventions()
    decision = next_transition(_evidence(phase), conv)
    assert decision.persona is conv.phase_machine[phase].agent
    assert decision.persona is not None


def test_next_transition_does_not_proceed_when_blocked():
    conv = _build_conventions()
    ev = _evidence(Phase.RED, validator_reports=(_blocking_report(),))
    decision = next_transition(ev, conv)
    assert decision.verdict.kind is VerdictKind.BLOCKED
    assert decision.to_phase is None
    assert decision.persona is None


@pytest.mark.parametrize("phase", [Phase.COMPLETE, Phase.OBSOLETE])
def test_next_transition_terminal_phase_has_no_forward(phase: Phase):
    conv = _build_conventions()
    decision = next_transition(_evidence(phase), conv)
    assert decision.to_phase is None


# --------------------------------------------------------------------------- #
# evaluate_evidence                                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("phase", _ADVANCING_PHASES)
def test_evaluate_evidence_returns_verdict_with_rule_ids(phase: Phase):
    conv = _build_conventions()
    verdict = evaluate_evidence(_evidence(phase), conv)
    assert isinstance(verdict, Verdict)
    assert verdict.kind in set(VerdictKind)
    assert verdict.rule_ids  # non-empty


def test_evaluate_evidence_blocks_on_blocking_report():
    conv = _build_conventions()
    ev = _evidence(Phase.GREEN, validator_reports=(_blocking_report(),))
    verdict = evaluate_evidence(ev, conv)
    assert verdict.kind is VerdictKind.BLOCKED
    assert "coach.core.example.block" in verdict.rule_ids


@pytest.mark.parametrize("ci", [CiState.PENDING, CiState.NONE])
def test_evaluate_evidence_stays_when_ci_not_ready(ci: CiState):
    conv = _build_conventions()
    verdict = evaluate_evidence(_evidence(Phase.GREEN, ci_state=ci), conv)
    assert verdict.kind is VerdictKind.STAY
    assert verdict.retry_after_seconds is not None


# --------------------------------------------------------------------------- #
# review_phase_output                                                        #
# --------------------------------------------------------------------------- #

def test_review_phase_output_proceeds_with_clean_reports():
    conv = _build_conventions()
    verdict = review_phase_output(Phase.RED, (), conv)
    assert verdict.kind is VerdictKind.PROCEED
    assert verdict.rule_ids


def test_review_phase_output_blocks_on_blocking_report():
    conv = _build_conventions()
    verdict = review_phase_output(Phase.RED, (_blocking_report(),), conv)
    assert verdict.kind is VerdictKind.BLOCKED


# --------------------------------------------------------------------------- #
# merge_readiness                                                            #
# --------------------------------------------------------------------------- #

def test_merge_readiness_true_at_refactor_with_open_pr_and_green_ci():
    conv = _build_conventions()
    pr = PrState(
        number=999,
        state="OPEN",
        mergeable="MERGEABLE",
        merge_state="CLEAN",
        head_sha="a" * 40,
        check_runs=(),
        reviews=(),
        closes_issues=(888,),
    )
    ev = _evidence(Phase.REFACTOR, pr_state=pr, ci_state=CiState.SUCCESS)
    verdict = merge_readiness(ev, conv)
    assert isinstance(verdict, MergeVerdict)
    assert verdict.can_merge is True
    assert verdict.blockers == ()


def test_merge_readiness_false_when_no_pr():
    conv = _build_conventions()
    ev = _evidence(Phase.REFACTOR, pr_state=None)
    verdict = merge_readiness(ev, conv)
    assert verdict.can_merge is False
    assert verdict.blockers


def test_merge_readiness_false_early_phase():
    conv = _build_conventions()
    verdict = merge_readiness(_evidence(Phase.RED), conv)
    assert verdict.can_merge is False


# --------------------------------------------------------------------------- #
# escalation_for                                                            #
# --------------------------------------------------------------------------- #

def test_escalation_for_returns_none_when_healthy():
    conv = _build_conventions()
    assert escalation_for(_evidence(Phase.RED, elapsed_in_phase_seconds=5), conv) is None


def test_escalation_for_escalates_on_no_progress_ttl():
    """I-7: a stuck run beyond the no-progress TTL escalates."""
    conv = _build_conventions()
    ev = _evidence(Phase.RED, elapsed_in_phase_seconds=10 ** 9)
    verdict = escalation_for(ev, conv)
    assert verdict is not None
    assert verdict.kind is VerdictKind.ESCALATE


# --------------------------------------------------------------------------- #
# Purity / determinism — same inputs always produce the same output.          #
# --------------------------------------------------------------------------- #

def test_all_functions_are_deterministic():
    conv = _build_conventions()
    ev = _evidence(Phase.GREEN)
    assert next_transition(ev, conv) == next_transition(ev, conv)
    assert evaluate_evidence(ev, conv) == evaluate_evidence(ev, conv)
    assert review_phase_output(Phase.GREEN, (), conv) == review_phase_output(Phase.GREEN, (), conv)
    assert merge_readiness(ev, conv) == merge_readiness(ev, conv)
    assert escalation_for(ev, conv) == escalation_for(ev, conv)


def test_imported_names_are_callable():
    for fn in (next_transition, evaluate_evidence, review_phase_output,
               merge_readiness, escalation_for):
        assert callable(fn)
