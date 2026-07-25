# Phase: SPIKE
# Layer: integration
# Assertion: behavioral
"""SPIKE #1602 — prove the smoke-execution gate is fail-closed, both directions.

This test IS the spike's deliverable. The proposal claims a ``GateCheck``
registered for ``SMOKE->REFACTOR`` blocks the transition when smoke did not
execute, and that fail-closed comes free from ``decision.run_checks``. A green
result that cannot distinguish "smoke ran" from "smoke didn't" would be worth
nothing — that is the exact bug class this whole audit exists to close — so all
three fault injections run against the REAL transition path
(``IssueLifecycle.transition`` -> ``apply_transition`` -> ``_transition_gate``),
and "did not occur" is proven behaviorally via a recording spy on
``IssueManager.update`` (the label/phase swap), never by scraping stdout.

    1. no attestation        -> transition BLOCKED   (the bug being closed)
    2. passing attestation   -> transition PROCEEDS  (the negative control —
                                without this, blocking everything would "pass")
    3. check raises          -> transition BLOCKED   (fail-closed inheritance)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch

from atdd.coach.commands.issue_lifecycle import IssueLifecycle
from atdd.coach.gate.registrations import register_smoke_execution_check
from atdd.coach.gate.registry import GATE_REGISTRY
from atdd.coach.gate.smoke_execution_check import (
    GATE_ID,
    SmokeExecutionGateCheck,
    attestation_relpath,
)

pytestmark = [pytest.mark.platform]

ISSUE = 1602

# The one config line that turns enforcement on (proposal edit 4). Supplied by
# the test rather than committed to .atdd/config.yaml — the spike proves the
# mechanism without switching the repo's own SMOKE->REFACTOR gate on.
GATED_CONFIG = {"gate": {"transitions": {"SMOKE->REFACTOR": True}}}


@pytest.fixture
def smoke_issue():
    """An issue sitting in SMOKE, so from_phase resolves to SMOKE."""
    return {
        "number": ISSUE,
        "title": "SPIKE: fail-closed smoke-execution gate",
        "state": "OPEN",
        "labels": [{"name": "atdd-issue"}, {"name": "atdd:SMOKE"}],
        "body": "",
    }


@pytest.fixture
def clean_registry():
    """Isolate SMOKE->REFACTOR so only the check under test can vote."""
    before = GATE_REGISTRY.checks_for("SMOKE", "REFACTOR")
    GATE_REGISTRY.clear("SMOKE", "REFACTOR")
    yield GATE_REGISTRY
    GATE_REGISTRY.clear("SMOKE", "REFACTOR")
    for chk in before:
        GATE_REGISTRY.register("SMOKE", "REFACTOR", chk)


def _write_attestation(worktree: Path, runs: list) -> Path:
    """Hand-place a fixture attestation to simulate "smoke ran".

    The real writer is a pytest hook the full build owns; the spike only needs
    the READ side to be provably discriminating.
    """
    path = worktree / attestation_relpath(ISSUE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"runs": runs}))
    return path


def _attempt_transition(worktree: Path, issue: dict) -> tuple[int, MagicMock]:
    """Drive the real SMOKE->REFACTOR transition; return (rc, update spy)."""
    lifecycle = IssueLifecycle(target_dir=worktree)
    update_spy = MagicMock(return_value=0)
    with patch.object(IssueLifecycle, "_fetch_issue", return_value=issue), \
         patch.object(IssueLifecycle, "_load_config", return_value=GATED_CONFIG), \
         patch.object(IssueLifecycle, "_compliance_gate", return_value=0), \
         patch.object(IssueLifecycle, "_reenter_display_only", return_value=0), \
         patch("atdd.coach.commands.issue.IssueManager.update", update_spy):
        rc = lifecycle.transition(ISSUE, "REFACTOR", force=False)
    return rc, update_spy


# --------------------------------------------------------------------------- #
# Fault injection 1 — no attestation => BLOCKED (the bug being closed)         #
# --------------------------------------------------------------------------- #


def test_no_attestation_blocks_smoke_to_refactor(tmp_path: Path, smoke_issue, clean_registry):
    """Smoke never ran (no attestation) => SMOKE->REFACTOR must not occur."""
    register_smoke_execution_check(clean_registry)
    assert not (tmp_path / attestation_relpath(ISSUE)).exists()

    rc, update_spy = _attempt_transition(tmp_path, smoke_issue)

    assert rc != 0, "a missing smoke-execution attestation must return non-zero"
    assert not update_spy.called, (
        "SMOKE->REFACTOR occurred with no proof that smoke ever executed — "
        "IssueManager.update() (the label/phase swap) must never be reached"
    )


# --------------------------------------------------------------------------- #
# Fault injection 2 — attestation present => PROCEEDS (the negative control)   #
# --------------------------------------------------------------------------- #


def test_passing_attestation_allows_smoke_to_refactor(tmp_path: Path, smoke_issue, clean_registry):
    """Smoke ran and passed => the gate must let the transition through.

    Without this control the suite could not tell a working gate from one that
    blocks unconditionally.
    """
    register_smoke_execution_check(clean_registry)
    _write_attestation(tmp_path, [
        {"nodeid": "tests/smoke/test_live.py::test_end_to_end",
         "outcome": "passed", "duration_s": 4.2},
    ])

    rc, update_spy = _attempt_transition(tmp_path, smoke_issue)

    assert rc == 0, "a passing smoke-execution attestation must not block the transition"
    assert update_spy.called, (
        "the gate blocked SMOKE->REFACTOR despite a passing smoke attestation — "
        "a gate that blocks everything proves nothing"
    )


# --------------------------------------------------------------------------- #
# Fault injection 3 — check raises => BLOCKED (fail-closed inheritance)        #
# --------------------------------------------------------------------------- #


def test_raising_check_blocks_rather_than_allows(tmp_path: Path, smoke_issue, clean_registry):
    """An exploding check must FAIL the transition, not wave it through.

    Proves the claim that fail-closed is inherited free from
    ``decision.run_checks`` — the check itself catches nothing here. The
    attestation is present and valid, so a fail-OPEN aggregator would be
    indistinguishable from injection 2; only the raise can make this block.
    """
    register_smoke_execution_check(clean_registry)
    _write_attestation(tmp_path, [{"nodeid": "x::y", "outcome": "passed", "duration_s": 4.2}])

    boom = MagicMock(side_effect=RuntimeError("attestation store unreachable"))
    with patch.object(SmokeExecutionGateCheck, "run", boom):
        rc, update_spy = _attempt_transition(tmp_path, smoke_issue)

    assert boom.called, "the injected raise never ran — the check was not consulted"
    assert rc != 0, "an errored gate check must fail closed (non-zero), not pass silently"
    assert not update_spy.called, (
        "SMOKE->REFACTOR occurred while the gate check was erroring — "
        "fail-closed inheritance from run_checks is broken"
    )


# --------------------------------------------------------------------------- #
# Supporting proofs — the discriminating read, and the registration seam       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "payload, why",
    [
        ('{"runs": []}', "an attestation recording no runs"),
        ('{"runs": [{"nodeid": "x::y", "outcome": "skipped"}]}',
         "an all-skipped run (#1076 class: 'passed' by skipping)"),
        ('{"runs": [{"nodeid": "x::y", "outcome": "failed"}]}', "a failing run"),
        ("{not json", "a corrupt/unparseable attestation"),
        ('"a string"', "a well-formed JSON document of the wrong shape"),
    ],
)
def test_degenerate_attestations_do_not_satisfy_the_gate(tmp_path: Path, payload, why):
    """The read must discriminate — mere presence of a file is not evidence."""
    from atdd.coach.gate.decision import GateContext

    path = tmp_path / attestation_relpath(ISSUE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)

    ctx = GateContext(issue_number=ISSUE, from_phase="SMOKE",
                      to_phase="REFACTOR", worktree=tmp_path)
    result = SmokeExecutionGateCheck().run(ctx)

    assert not result.passed, f"{why} must not satisfy the smoke-execution gate"


def test_operator_typed_stamp_is_not_accepted_as_execution_evidence(tmp_path: Path):
    """The #358 presentation-ratchet stamp must not satisfy this gate.

    ``.atdd/smoke-evidence/<N>.yaml`` is producible by hand with
    ``atdd validate coder --smoke-required`` without running a test. If reading
    it satisfied this gate, the spike would have re-imported the bug.
    """
    from atdd.coach.gate.decision import GateContext

    stamp = tmp_path / ".atdd" / "smoke-evidence" / f"{ISSUE}.yaml"
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(
        f"issue: {ISSUE}\n"
        "note: recorded via `atdd validate coder --smoke-required`\n"
        "recorded_by: alecfokapu\n"
    )

    ctx = GateContext(issue_number=ISSUE, from_phase="SMOKE",
                      to_phase="REFACTOR", worktree=tmp_path)
    result = SmokeExecutionGateCheck().run(ctx)

    assert not result.passed, (
        "an operator-typed stamp satisfied the smoke-EXECUTION gate — "
        "that is the exact bug class this gate exists to close"
    )


def test_registration_is_idempotent_and_targets_smoke_to_refactor(clean_registry):
    """The registration seam: one check, on SMOKE->REFACTOR, however often called."""
    register_smoke_execution_check(clean_registry)
    register_smoke_execution_check(clean_registry)

    checks = clean_registry.checks_for("SMOKE", "REFACTOR")
    assert [c.gate_id for c in checks].count(GATE_ID) == 1, (
        "register_smoke_execution_check must be idempotent"
    )
    assert not any(
        getattr(c, "gate_id", None) == GATE_ID
        for c in clean_registry.checks_for("GREEN", "SMOKE")
    ), "the smoke-execution check must not leak onto other transitions"
