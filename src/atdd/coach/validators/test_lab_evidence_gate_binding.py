# URN: component:govern-lifecycle:enforce-lab-evidence:test_lab_evidence_gate_binding:backend:application
# Runtime: python
# Purpose: Bind coach.lifecycle.no-init-to-planned-without-lab to its live mechanism — the #1950 INIT->PLANNED gate check — and fail if that wiring is ever cut.

"""The mechanism guard for ``coach.lifecycle.no-init-to-planned-without-lab``.

Modelled on ``test_smoke_execution_gate_binding`` and for the same reason (#399
reverse coherence): a rule that claims enforcement must name a validator that
literally binds it, so it can never quietly become a mechanism-less claim.

WIRING IS WHAT ROTS SILENTLY, and this rule has more of it than most. Delete the
``register_lab_evidence_check()`` call at the transition dispatch, rename the
check's ``rule_id``, or point the unfilled-marker read at a local copy of the
scaffold instead of the generator's ``LAB_SCAFFOLD`` — each is a one-line edit, each
leaves the gate existing while enforcing less than it says, and none would fail any
other test in the repo.

THE FOURTH FAULT IS SPECIFIC TO THIS RULE. The gate's honesty rests on reading the
generator's exported scaffold rather than pattern-matching at prose: #1950's lab
measured the guessing version at 3 of 4 prompts, silently missing ``### Hypothesis``
over a comma in its text. So a fault is raised if the two surfaces stop agreeing —
if the planner stops exporting ``LAB_SCAFFOLD``, or the gate stops recognising what
the generator actually writes.

SCOPE, stated plainly. This asserts the gate is CONNECTED, not that it is CORRECT
(that is ``src/atdd/coach/gate/tests/test_e083_*``), and not that it is ENFORCING in
this repo. Enforcement is one line of ``.atdd/config.yaml`` per repo by design
(``is_transition_gated``), and for this rule it is deliberately NOT set here:
``INIT->PLANNED`` has no per-issue opt-in, so enabling it would refuse every
in-flight issue lacking a lab. Asserting a local config value here would make the
toolkit's own operator choice a convention violation for every consumer.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List

import pytest

import atdd
from atdd.coach.gate.lab_evidence_check import GATE_ID, LabEvidenceGateCheck, lab_violations
from atdd.coach.gate.registrations import register_lab_evidence_check
from atdd.coach.gate.registry import GateRegistry
from atdd.coach.utils.rule_binding import bind_rule

pytestmark = [pytest.mark.coach]

_RULE = bind_rule("coach.lifecycle.no-init-to-planned-without-lab")

#: Where the check must be registered for the rule to have any effect at all.
_TRANSITION = ("INIT", "PLANNED")

#: The verb dispatch that must call the registration. Named as a path rather than
#: imported-and-introspected because the call is a statement, not a value.
_DISPATCH = Path(atdd.__file__).resolve().parent / "coach" / "commands" / "issue_transition.py"
_REGISTRAR = "register_lab_evidence_check"


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


def _scaffold_is_read_not_guessed() -> List[str]:
    """The gate must recognise what the generator actually writes.

    Asked behaviourally rather than by reading source: build a body from the live
    ``LAB_SCAFFOLD`` and require every subsection to come back unfilled. A gate
    carrying its own copy of the prompts passes today and fails the day one is
    reworded — which is the silent half of this rule's wiring.
    """
    try:
        from atdd.planner.commands.author_issue import LAB_SCAFFOLD
    except Exception as exc:  # the export is the wiring under test
        return [
            f"the planner no longer exports LAB_SCAFFOLD ({exc}), so the gate has no "
            f"source for the scaffold strings and must guess at them"
        ]

    names = ("Hypothesis", "Setup", "Measured result", "What it changed about the plan")
    missing = [n for n in names if n not in LAB_SCAFFOLD]
    if missing:
        return [f"LAB_SCAFFOLD does not declare {missing} — the gate cannot recognise them"]

    lines = ["# probe", "", "## Lab", ""]
    for name in names:
        lines += [f"### {name}", "", LAB_SCAFFOLD[name], ""]
    lines += ["## Phases", ""]
    unrecognised = [n for n in names if not any(n in v for v in lab_violations("\n".join(lines)))]
    if unrecognised:
        return [
            f"the gate does not recognise the generator's own scaffold for "
            f"{unrecognised} — it is matching its own copy of the prompts rather than "
            f"reading LAB_SCAFFOLD, which is the 3-of-4 failure #1950's lab measured"
        ]
    return []


def _wiring_faults() -> List[str]:
    """Every way the rule could be enforced-on-paper but disarmed in fact."""
    faults: List[str] = []

    check = LabEvidenceGateCheck()
    if check.rule_id != _RULE.rule_id:
        faults.append(
            f"LabEvidenceGateCheck declares rule_id {check.rule_id!r}, not "
            f"{_RULE.rule_id!r} — the rule names a mechanism that no longer names it back"
        )
    # Asked structurally rather than with `isinstance(check, GateCheck)`, which the
    # precedent uses. Both assert the same thing — a runtime_checkable Protocol can
    # only check member presence, never signatures — but the isinstance form reports
    # pyright's reportGeneralTypeIssues ("overlaps unsafely"), and the precedent's copy
    # of that finding is grandfathered into .atdd/baselines/types_toolkit.yaml. Adding
    # a second copy of a known finding to a ratchet baseline is the opposite of what
    # the ratchet is for, so the assertion is written the way that needs no entry.
    if not callable(getattr(check, "run", None)):
        faults.append(
            "LabEvidenceGateCheck no longer satisfies the #1020 GateCheck Protocol "
            "(no callable `run`), so the registry cannot run it"
        )

    registry = GateRegistry()
    register_lab_evidence_check(registry)
    if not any(getattr(c, "gate_id", None) == GATE_ID for c in registry.checks_for(*_TRANSITION)):
        faults.append(
            f"{_REGISTRAR}() does not register the check for "
            f"{_TRANSITION[0]}->{_TRANSITION[1]}"
        )

    if not _dispatch_calls_registrar():
        faults.append(
            f"{_DISPATCH.name} no longer calls {_REGISTRAR}() at the transition dispatch, "
            "so the check can never be consulted however the repo is configured"
        )

    faults.extend(_scaffold_is_read_not_guessed())
    return faults


def test_no_init_to_planned_without_lab_has_a_live_mechanism() -> None:
    """The rule's enforcement path exists end to end, or this fails loudly."""
    faults = _wiring_faults()
    if not faults:
        return
    formatted = "\n".join(f"  - {fault}" for fault in faults)
    pytest.fail(
        f"\n{len(faults)} wiring fault(s) leave {_RULE.rule_id} declared but "
        f"disarmed:\n\n{formatted}\n\n"
        "Restore the wiring: LabEvidenceGateCheck must declare "
        f"rule_id={_RULE.rule_id!r}, {_REGISTRAR}() must register it for "
        "INIT->PLANNED, issue_transition must call that registrar at dispatch, and the "
        "unfilled-marker read must come from the generator's LAB_SCAFFOLD. If the rule "
        "is genuinely no longer enforced, set its metadata.disposition back to "
        "documentation-only and delete this validator — but do not leave a rule claiming "
        "enforcement it does not have."
    )
