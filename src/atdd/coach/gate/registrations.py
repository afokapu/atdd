"""Config-gated registration of the operator-approval check INTO the #1020 gate.

This module performs a SIDE EFFECT on import: it registers an
``ApprovalTokenGateCheck`` into the module-level ``GATE_REGISTRY`` for the
operator-gateable phase transitions, so the worker's
``atdd issue <N> --status <next>`` is refused until an operator-signed token
exists.

``register_approval_checks()`` is called EXPLICITLY at the ``atdd issue
--status`` CLI dispatch — NOT as an import-time side effect, and NOT from the
gate package ``__init__``. Importing this module must stay pure: a side-effect
registration into the module-level ``GATE_REGISTRY`` would pollute it for the
#1020 migration-safety tests (and #1017's own integration/smoke tests) that
assert behaviour against the live registry, since test collection imports every
module. Which transitions actually ENFORCE is decided by ``is_transition_gated``
(``.atdd/config.yaml`` ``gate.transitions``, default PLANNED->RED only);
registering the check here merely makes it AVAILABLE for those transitions to
consult, so an operator can turn any phase gate on via config without a code
change.
"""
from __future__ import annotations

from atdd.coach.gate.approval_check import GATE_ID, ApprovalTokenGateCheck
from atdd.coach.gate.registry import GATE_REGISTRY
from atdd.coach.gate.smoke_execution_check import (
    GATE_ID as SMOKE_EXECUTION_GATE_ID,
    SmokeExecutionGateCheck,
)

# The candidate operator-gateable lifecycle transitions. ``is_transition_gated``
# decides which actually enforce (default: only PLANNED->RED). Creating the plan
# (INIT->PLANNED) is not an operator-reserved sign-off, so it is intentionally
# absent.
_CANDIDATE_TRANSITIONS = (
    ("PLANNED", "RED"),
    ("RED", "GREEN"),
    ("GREEN", "SMOKE"),
    ("SMOKE", "REFACTOR"),
    ("REFACTOR", "COMPLETE"),
)


def register_approval_checks(registry=GATE_REGISTRY) -> None:
    """Idempotently register the approval check for the candidate transitions."""
    for from_phase, to_phase in _CANDIDATE_TRANSITIONS:
        existing = registry.checks_for(from_phase, to_phase)
        if any(getattr(c, "gate_id", None) == GATE_ID for c in existing):
            continue
        registry.register(from_phase, to_phase, ApprovalTokenGateCheck())


# The transition the smoke-execution attestation gates. Already present in
# ``_CANDIDATE_TRANSITIONS`` above, so the seam it plugs into is the proven one.
_SMOKE_EXECUTION_TRANSITION = ("SMOKE", "REFACTOR")


def register_smoke_execution_check(registry=GATE_REGISTRY) -> None:
    """Idempotently register the smoke-execution check for SMOKE->REFACTOR.

    SPIKE (#1602) — REGISTRATION HELPER ONLY. Like ``register_approval_checks``
    this is deliberately NOT an import-time side effect (that would pollute
    ``GATE_REGISTRY`` for #1020's migration-safety tests, which assert against
    the live registry that test collection imports every module into).

    Unlike ``register_approval_checks`` it is not yet called from the
    ``atdd coach transition`` dispatch, and ``.atdd/config.yaml`` does not yet
    carry ``SMOKE->REFACTOR: true`` — so in this repo the check is AVAILABLE but
    not ENFORCING. Turning it on repo-wide is the full build's job, gated on
    this spike's proof.
    """
    from_phase, to_phase = _SMOKE_EXECUTION_TRANSITION
    existing = registry.checks_for(from_phase, to_phase)
    if any(getattr(c, "gate_id", None) == SMOKE_EXECUTION_GATE_ID for c in existing):
        return
    registry.register(from_phase, to_phase, SmokeExecutionGateCheck())
