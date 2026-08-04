# URN: component:govern-lifecycle:enforcement-substrate:test_smoke_execution_gate_binding:backend:application
# Runtime: python
# Purpose: Bind coach.lifecycle.no-green-to-refactor-without-smoke to its live mechanism — the #1602 SMOKE->REFACTOR gate check — and fail if that wiring is ever cut.

"""The mechanism guard for ``coach.lifecycle.no-green-to-refactor-without-smoke``.

The rule says: *real-infrastructure SMOKE must run before REFACTOR.* Until #1602
nothing enforced it, so the node shipped ``disposition: documentation-only`` —
honestly. It now has a mechanism (``SmokeExecutionGateCheck``, registered for
``SMOKE->REFACTOR``, reading an attestation only a live-smoke run can write), and
``documentation-only`` would be the dishonest label.

What flipping the disposition costs is this file, and that is the point of it.
Reverse coherence (#399) demands that an enforced rule name a validator which
literally binds it, so the rule can never quietly become a mechanism-less claim
again. The mechanism this validator guards is *wiring*, and wiring is exactly what
rots silently: delete the ``register_smoke_execution_check()`` call at the
enforcement seam, or rename the check's ``rule_id``, and the gate goes on
existing while enforcing nothing. Both are one-line edits that no other test in
the repo would notice.

SCOPE, stated plainly. This validator asserts the gate is CONNECTED. It does not
assert the gate is CORRECT — that is
``src/atdd/coach/gate/tests/test_1602_smoke_execution_end_to_end.py``, which runs
a real pytest over a real live_smoke acceptance and checks the verdict in both
directions. Nor does it assert the gate is ENFORCING in this repo: enforcement is
one line of ``.atdd/config.yaml`` per repo by design (``is_transition_gated``),
and asserting a local config value here would make the toolkit's own operator
choice a convention violation for every consumer.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List

import pytest

import atdd
from atdd.coach.gate.decision import GateCheck
from atdd.coach.gate.registry import GateRegistry
from atdd.coach.gate.registrations import register_smoke_execution_check
from atdd.coach.gate.smoke_execution_check import GATE_ID, SmokeExecutionGateCheck
from atdd.coach.utils.rule_binding import bind_rule

pytestmark = [pytest.mark.coach]

_RULE = bind_rule("coach.lifecycle.no-green-to-refactor-without-smoke")

#: Where the check must be registered for the rule to have any effect at all.
_TRANSITION = ("SMOKE", "REFACTOR")

#: The seam that must call the registration. Named as a path rather than
#: imported-and-introspected because the call is a statement, not a value: only
#: reading the source can tell whether it is still there.
#:
#: MOVED BY #1619, and the move is the point. This pointer used to name
#: ``coach/commands/issue_transition.py`` — the ``atdd coach transition`` verb
#: dispatch — because that was the only thing in the tree that registered. That
#: was the defect: it made the registry's contents depend on HOW a transition was
#: invoked rather than on WHICH edge was crossed, so four other phase-advancing
#: paths evaluated an empty registry. Registration now lives at the gate
#: evaluation seam, where every path reaches it. This guard follows the wiring it
#: guards; it was not suppressed and its assertion is not weakened.
_DISPATCH = Path(atdd.__file__).resolve().parent / "coach" / "gate" / "enforcement.py"
_REGISTRAR = "register_smoke_execution_check"


def _dispatch_calls_registrar() -> bool:
    """True iff ``issue_transition.py`` still calls the registrar at dispatch."""
    tree = ast.parse(_DISPATCH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == _REGISTRAR:
            return True
    return False


def _wiring_faults() -> List[str]:
    """Every way the rule could be enforced-on-paper but disarmed in fact."""
    faults: List[str] = []

    check = SmokeExecutionGateCheck()
    if check.rule_id != _RULE.rule_id:
        faults.append(
            f"SmokeExecutionGateCheck declares rule_id {check.rule_id!r}, not "
            f"{_RULE.rule_id!r} — the rule names a mechanism that no longer names it back"
        )
    if not isinstance(check, GateCheck):
        faults.append(
            "SmokeExecutionGateCheck no longer satisfies the #1020 GateCheck Protocol, "
            "so the registry cannot run it"
        )

    registry = GateRegistry()
    register_smoke_execution_check(registry)
    registered = registry.checks_for(*_TRANSITION)
    if not any(getattr(c, "gate_id", None) == GATE_ID for c in registered):
        faults.append(
            f"{_REGISTRAR}() does not register the check for "
            f"{_TRANSITION[0]}->{_TRANSITION[1]}"
        )

    if not _dispatch_calls_registrar():
        faults.append(
            f"{_DISPATCH.name} no longer calls {_REGISTRAR}() at the transition "
            "dispatch, so the check can never be consulted however the repo is "
            "configured"
        )
    return faults


def test_no_green_to_refactor_without_smoke_has_a_live_mechanism() -> None:
    """The rule's enforcement path exists end to end, or this fails loudly."""
    faults = _wiring_faults()
    if not faults:
        return
    formatted = "\n".join(f"  - {fault}" for fault in faults)
    pytest.fail(
        f"\n{len(faults)} wiring fault(s) leave {_RULE.rule_id} declared but "
        f"disarmed:\n\n{formatted}\n\n"
        "Restore the wiring: SmokeExecutionGateCheck must declare "
        f"rule_id={_RULE.rule_id!r}, {_REGISTRAR}() must register it for "
        "SMOKE->REFACTOR, and issue_transition must call that registrar at "
        "dispatch. If the rule is genuinely no longer enforced, set its "
        "metadata.disposition back to documentation-only and delete this "
        "validator — but do not leave a rule claiming enforcement it does not have."
    )
