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


def approval_required_for(config, from_phase: str, to_phase: str) -> bool:
    """Whether crossing ``from_phase -> to_phase`` needs ``atdd coach approve`` first.

    The two declarations that decide it, asked together and asked of nothing
    else: :data:`_CANDIDATE_TRANSITIONS` (which edges the approval check is
    registered for) and :func:`~atdd.coach.gate.decision.is_transition_gated`
    (which of those the repo's ``.atdd/config.yaml`` actually enforces).

    Exists so a caller can DERIVE the operator's next command instead of
    restating it. ``atdd coach enter``'s next-step hint printed a bare
    ``atdd coach transition <N> RED`` for four issues on 2026-08-04 while this
    repo's config set ``PLANNED->RED: true``, so the only guidance the lifecycle
    offers named a command the gate would refuse (#1750). A hardcoded string
    there would go stale the moment a repo gates a different edge — which is the
    whole point of the config knob.

    Pure: reads the declarations, registers nothing and mutates no registry, so
    a read-only surface can ask without the import-time side effect this module's
    header forbids.
    """
    from atdd.coach.gate.decision import is_transition_gated

    if (from_phase, to_phase) not in _CANDIDATE_TRANSITIONS:
        return False
    return is_transition_gated(config, from_phase, to_phase)


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
    """Idempotently register the smoke-execution check for SMOKE->REFACTOR (#1602).

    Called explicitly from the ``atdd coach transition`` dispatch beside
    ``register_approval_checks``, and for the same reason deliberately NOT an
    import-time side effect: a side-effect registration into the module-level
    ``GATE_REGISTRY`` would pollute it for #1020's migration-safety tests, which
    assert against the live registry that test collection imports every module
    into.

    Registering makes the check AVAILABLE; ``is_transition_gated`` decides
    whether it ENFORCES. ``SMOKE->REFACTOR`` is absent from
    ``DEFAULT_GATED_TRANSITIONS``, so a repo turns it on with one line of
    ``.atdd/config.yaml``::

        gate:
          transitions:
            SMOKE->REFACTOR: true

    That line IS now set in this repo, and what made it safe to set is that the
    check is opt-in per issue (:mod:`atdd.coach.gate.smoke_obligation`): it holds
    an issue to a live-smoke run only when that issue's own plan scope declares an
    ``execution_kind: live_smoke`` acceptance, and passes as *not applicable*
    otherwise. Enabling it against an unconditional fail-closed check would have
    made ``SMOKE->REFACTOR`` unreachable for every in-flight issue except through
    ``--force`` — the bypass-advertising failure this whole issue exists to
    remove. A consumer repo turning this on inherits the same property: nothing is
    gated until something is declared.
    """
    from_phase, to_phase = _SMOKE_EXECUTION_TRANSITION
    existing = registry.checks_for(from_phase, to_phase)
    if any(getattr(c, "gate_id", None) == SMOKE_EXECUTION_GATE_ID for c in existing):
        return
    registry.register(from_phase, to_phase, SmokeExecutionGateCheck())
