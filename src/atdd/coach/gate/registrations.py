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
