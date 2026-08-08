# URN: test:govern-lifecycle:enforcing-phase-transition-gate:R011-UNIT-001-enforcement-seam-registers-before-evaluating
# Acceptance: acc:govern-lifecycle:R011-UNIT-001-enforcement-seam-registers-before-evaluating
# WMBT: wmbt:govern-lifecycle:R011
# Phase: RED
# Layer: unit
# Assertion: behavioral
# Purpose: the seam that decides a transition is the same seam that registers the checks, so the registry's contents depend on the edge being crossed rather than on which CLI verb ran
"""R011-UNIT-001 — registration is bound to gate EVALUATION, not to a CLI verb.

Root cause fact one (#1619): ``register_approval_checks`` and
``register_smoke_execution_check`` have exactly ONE non-test call site between
them — ``issue_transition.run``, the ``atdd coach transition`` verb dispatch. A
caller that never shelled out to that verb evaluates the gate against an empty
registry, so the gate does not fail to find a token; it never looks.

This pins the fix: whatever decides a transition must first perform the
registration itself. A caller handing the seam an empty registry — which is what
every non-CLI phase-advancing path effectively does — gets the checks registered
and then consulted.

The import-purity half is not decoration. ``registrations.py`` documents why
registration must NOT be an import-time side effect: it would pollute the
module-level ``GATE_REGISTRY`` for #1020's migration-safety tests, which assert
against the live registry that collection imports every module into. The seam
must therefore register when CALLED and never when IMPORTED, and that is checked
in a subprocess because within this process collection has already imported
everything.

RED state: ``atdd.coach.gate.enforcement`` does not exist.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from atdd.coach.gate.approval_check import GATE_ID as APPROVAL_GATE_ID, RULE_ID as APPROVAL_RULE_ID
from atdd.coach.gate.decision import GateContext, GateVerdict
from atdd.coach.gate.registry import GateRegistry
from atdd.coach.gate.smoke_execution_check import GATE_ID as SMOKE_GATE_ID

pytestmark = [pytest.mark.platform]

# Never a live issue: the repo's issues are in the low thousands.
_ISSUE = 999011
_GATED_CONFIG = {"gate": {"transitions": {"PLANNED->RED": True}}}


def test_seam_registers_the_checks_it_is_about_to_consult(tmp_path: Path):
    """R011-UNIT-001: an empty registry handed to the seam comes back populated."""
    from atdd.coach.gate.enforcement import enforce_transition_gate

    registry = GateRegistry()
    assert registry.is_empty(), "precondition: the caller has registered nothing"

    ctx = GateContext(
        issue_number=_ISSUE, from_phase="PLANNED", to_phase="RED", worktree=tmp_path
    )
    outcome = enforce_transition_gate(_GATED_CONFIG, ctx, registry=registry)

    # The seam registered what it needed, for the edge being crossed...
    planned_red = registry.checks_for("PLANNED", "RED")
    assert any(getattr(c, "gate_id", None) == APPROVAL_GATE_ID for c in planned_red), (
        "the approval check must be registered for PLANNED->RED by the seam itself, "
        "not by whichever CLI verb the caller happened to use"
    )
    # ...and for the other edge the production registrars cover, so the seam is
    # the whole registration, not a PLANNED->RED special case.
    smoke_refactor = registry.checks_for("SMOKE", "REFACTOR")
    assert any(getattr(c, "gate_id", None) == SMOKE_GATE_ID for c in smoke_refactor), (
        "register_smoke_execution_check must run at the same seam (#1602)"
    )

    # ...and having registered, it consulted them. No token exists under tmp_path.
    assert outcome.proceed is False, (
        "a gated edge with no approval token must refuse on a programmatic path "
        "exactly as it does on the CLI path"
    )
    blocking = outcome.blockers
    assert any(b.rule_id == APPROVAL_RULE_ID for b in blocking), (
        f"the refusal must be attributed to the approval check's bound rule; got "
        f"{[(b.gate_id, b.rule_id) for b in blocking]}"
    )
    # It LOOKED and found nothing — a FAIL, not a could-not-check. The
    # could-not-check verdict is reserved for the unregistered case (UNIT-002).
    approval_result = next(b for b in blocking if b.rule_id == APPROVAL_RULE_ID)
    assert approval_result.verdict is GateVerdict.FAIL


def test_registration_is_not_an_import_time_side_effect():
    """R011-UNIT-001: importing the seam must leave the live GATE_REGISTRY empty.

    Checked in a subprocess: inside THIS process pytest collection has already
    imported every module and may have called the seam, so the live registry's
    state here proves nothing either way.
    """
    probe = (
        "import atdd.coach.gate.enforcement\n"
        "from atdd.coach.gate.registry import GATE_REGISTRY\n"
        "assert GATE_REGISTRY.is_empty(), (\n"
        "    'importing the enforcement seam registered checks into the live '\n"
        "    'GATE_REGISTRY; that pollutes #1020/#1020-era migration-safety tests, '\n"
        "    'which is exactly why registrations.py refuses to register at import time'\n"
        ")\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, (
        f"import-time purity probe failed:\n{result.stdout}\n{result.stderr}"
    )
