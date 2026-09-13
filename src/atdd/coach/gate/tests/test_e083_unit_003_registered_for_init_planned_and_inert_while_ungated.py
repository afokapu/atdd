# URN: test:govern-lifecycle:enforce-lab-evidence:E083-UNIT-003-registered-for-init-planned-and-inert-while-ungated
# Acceptance: acc:govern-lifecycle:E083-UNIT-003-registered-for-init-planned-and-inert-while-ungated
# WMBT: wmbt:govern-lifecycle:E083
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E083-UNIT-003 — registered for INIT->PLANNED, and INERT until the edge is gated.

REGISTRATION IS NOT ENABLEMENT, and #1950's first plan conflated the two.
``evaluate_transition_gate`` asks ``is_transition_gated`` BEFORE it looks at the
registry, so ``GATE_REGISTRY.register("INIT", "PLANNED", ...)`` on its own produces
a check that never runs. Both halves need asserting, and they pull in opposite
directions — which is why they are one acceptance and not two.

WHY IT SHIPS INERT. Measured: with the edge gated repo-wide, this check refuses
**162 of 163** open-at-INIT issues, spread evenly across four months with no cutover
cliff. Unlike ``SmokeExecutionGateCheck`` there is no per-issue opt-in to soften it —
every issue has a premise, so nothing is ever "not applicable". Enabling it now would
make ``--force`` the routine exit, which is the rubber-stamp failure this repo's own
config comment warns about for ``SMOKE->REFACTOR``. So enablement is an operator
decision taken once the backlog is triaged, and the third test below is what keeps
landing the check from quietly becoming that decision.

REGISTERED AT DISPATCH, NEVER AT IMPORT — the constraint ``registrations.py``
states: a side-effect registration into the module-level ``GATE_REGISTRY`` would
pollute it for #1020's migration-safety tests, which assert against the live
registry that collection imports every module into.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.decision import GateContext, evaluate_transition_gate
from atdd.coach.gate.registry import GateRegistry

_EDGE = ("INIT", "PLANNED")


def _register():
    """The registration entry point, or fail naming the phase that lands it."""
    from atdd.coach.gate import registrations

    fn = getattr(registrations, "register_lab_evidence_check", None)
    assert fn is not None, (
        "registrations.register_lab_evidence_check() not implemented yet — #1950 "
        "GREEN. Nothing is registered for INIT->PLANNED today, so the edge is "
        "evidence-blind whether or not it is gated."
    )
    return fn


def _check_cls():
    try:
        from atdd.coach.gate.lab_evidence_check import LabEvidenceGateCheck
    except ImportError:  # pragma: no cover - the RED state
        pytest.fail(
            "atdd.coach.gate.lab_evidence_check.LabEvidenceGateCheck not implemented "
            "yet — #1950 GREEN."
        )
    return LabEvidenceGateCheck


def test_the_check_registers_for_the_init_planned_edge():
    registry = GateRegistry()
    _register()(registry)
    checks = registry.checks_for(*_EDGE)
    assert any(isinstance(c, _check_cls()) for c in checks), (
        f"no LabEvidenceGateCheck registered for {_EDGE[0]}->{_EDGE[1]}; got {checks}"
    )


def test_registration_is_idempotent():
    """Called at every dispatch, so calling twice must not double the check."""
    registry = GateRegistry()
    _register()(registry)
    _register()(registry)
    cls = _check_cls()
    assert sum(1 for c in registry.checks_for(*_EDGE) if isinstance(c, cls)) == 1


def test_importing_the_module_registers_nothing():
    """The constraint registrations.py states: no import-time side effect."""
    import importlib

    from atdd.coach.gate.registry import GATE_REGISTRY

    before = len(GATE_REGISTRY.checks_for(*_EDGE))
    importlib.reload(importlib.import_module("atdd.coach.gate.lab_evidence_check"))
    assert len(GATE_REGISTRY.checks_for(*_EDGE)) == before, (
        "importing lab_evidence_check registered into the module-level GATE_REGISTRY; "
        "registration belongs at the transition dispatch (see registrations.py)"
    )


def test_the_gate_is_inert_while_the_edge_is_ungated(tmp_path: Path):
    """Registered, but the transition proceeds — whatever the body says.

    The config decides. With INIT->PLANNED absent from `gate.transitions`, and
    absent from DEFAULT_GATED_TRANSITIONS, `evaluate_transition_gate` returns before
    it ever consults the registry.
    """
    registry = GateRegistry()
    _register()(registry)
    ctx = GateContext(issue_number=1, from_phase="INIT", to_phase="PLANNED", worktree=tmp_path)
    outcome = evaluate_transition_gate(registry, {}, ctx)
    assert outcome.proceed, (
        "landing this check must not start refusing in-flight issues; it is inert "
        "until an operator gates the edge in .atdd/config.yaml"
    )


def test_the_gate_enforces_once_the_edge_is_gated(tmp_path: Path):
    """The other half — otherwise 'inert' would be indistinguishable from 'broken'."""
    registry = GateRegistry()
    _register()(registry)
    config = {"gate": {"transitions": {"INIT->PLANNED": True}}}
    ctx = GateContext(issue_number=1, from_phase="INIT", to_phase="PLANNED", worktree=tmp_path)
    outcome = evaluate_transition_gate(registry, config, ctx)
    assert not outcome.proceed, (
        "with the edge gated and an unresolvable issue body, the check must refuse "
        "(fail-closed); a gate that advances on an unmade observation is the defect"
    )
