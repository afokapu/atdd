# URN: test:govern-lifecycle:enforcing-phase-transition-gate:D019-UNIT-003-the-next-step-hint-names-a-runnable-command
# Acceptance: acc:govern-lifecycle:D019-UNIT-003-the-next-step-hint-names-a-runnable-command
# WMBT: wmbt:govern-lifecycle:D019
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The lifecycle's next-step hint is derived from the same gated-edge declarations the gate consults, so it never names a transition the gate will refuse and never invents an approval step for an ungated edge.
"""GREEN test for D019-UNIT-003 — the hint and the gate read one declaration.

`.atdd/config.yaml` in this repo sets `PLANNED->RED: true`, so that edge needs
`atdd coach approve <N> --transition 'PLANNED->RED'` before the transition is
accepted. The banner printed the bare transition on four issues on 2026-08-04
(#1750): the only guidance the lifecycle offers, at exactly the point where it
demands a human decision, named a command that would be refused.

D019 owns `is_transition_gated` — "which edges are gated, and the gate ships
inert". The hint being unable to answer that question is this WMBT's obligation
failing on the operator-facing side, so the fix is a DERIVATION, not a second
copy of the policy: flipping config must flip the sentence with no code change.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.gate.registrations import approval_required_for

pytestmark = [pytest.mark.platform]

ISSUE = 174


def _lifecycle(tmp_path: Path, config: dict):
    """An IssueLifecycle whose `.atdd/config.yaml` holds *config*."""
    from atdd.coach.commands.issue_lifecycle import IssueLifecycle

    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text(
        yaml.safe_dump({"version": "1.0", **config}), encoding="utf-8"
    )
    return IssueLifecycle(target_dir=tmp_path)


# --------------------------------------------------------------------------- #
# The derivation                                                              #
# --------------------------------------------------------------------------- #


def test_the_default_gated_edge_needs_an_approval_and_an_ungated_one_does_not() -> None:
    assert approval_required_for({}, "PLANNED", "RED") is True
    assert approval_required_for({}, "GREEN", "SMOKE") is False


def test_config_moves_the_answer_without_a_code_change() -> None:
    """The knob D019 exists to protect, read by the hint rather than restated."""
    config = {"gate": {"transitions": {"PLANNED->RED": False, "SMOKE->REFACTOR": True}}}

    assert approval_required_for(config, "PLANNED", "RED") is False
    assert approval_required_for(config, "SMOKE", "REFACTOR") is True


def test_an_edge_the_approval_check_does_not_cover_is_never_claimed() -> None:
    """Gated is not the same as approval-gated.

    `INIT->PLANNED` is deliberately absent from the approval check's candidate
    edges — creating the plan is not an operator-reserved sign-off — so gating it
    must not make the hint prescribe a mint that would authorise nothing.
    """
    config = {"gate": {"transitions": {"INIT->PLANNED": True}}}

    assert approval_required_for(config, "INIT", "PLANNED") is False


def test_asking_registers_nothing() -> None:
    """Pure: the header forbids an import-time registration side effect."""
    from atdd.coach.gate.registry import GATE_REGISTRY

    before = len(GATE_REGISTRY.checks_for("PLANNED", "RED"))
    approval_required_for({}, "PLANNED", "RED")

    assert len(GATE_REGISTRY.checks_for("PLANNED", "RED")) == before


# --------------------------------------------------------------------------- #
# The sentence the operator reads                                             #
# --------------------------------------------------------------------------- #


def test_a_gated_edge_names_the_approval_step(tmp_path, capsys) -> None:
    lifecycle = _lifecycle(tmp_path, {"gate": {"transitions": {"PLANNED->RED": True}}})

    lifecycle._print_next_action("PLANNED", ISSUE)
    out = capsys.readouterr().out

    assert f"atdd coach approve {ISSUE} --transition 'PLANNED->RED'" in out, (
        "the hint still names only the transition, which the gate will refuse:\n"
        f"{out}"
    )
    assert f"atdd coach transition {ISSUE} RED" in out, (
        "the transition itself dropped out of the hint; the operator needs both"
    )
    assert out.index("approve") < out.index("transition 174 RED"), (
        "the approval is printed after the command it must precede"
    )


def test_an_ungated_edge_names_only_the_transition(tmp_path, capsys) -> None:
    lifecycle = _lifecycle(tmp_path, {"gate": {"transitions": {"RED->GREEN": False}}})

    lifecycle._print_next_action("RED", ISSUE)
    out = capsys.readouterr().out

    assert f"atdd coach transition {ISSUE} GREEN" in out
    assert "approve" not in out, (
        f"the hint invented an approval step for an ungated edge:\n{out}"
    )


def test_turning_the_gate_off_removes_the_approval_from_the_hint(tmp_path, capsys) -> None:
    """Same phase, same code, opposite config — the sentence follows the policy."""
    lifecycle = _lifecycle(tmp_path, {"gate": {"transitions": {"PLANNED->RED": False}}})

    lifecycle._print_next_action("PLANNED", ISSUE)
    out = capsys.readouterr().out

    assert f"atdd coach transition {ISSUE} RED" in out
    assert "approve" not in out


def test_the_hint_agrees_with_the_gate_for_every_edge_the_machine_declares(
    tmp_path, capsys
) -> None:
    """No edge may be described one way and judged another.

    Enumerated from the phase machine rather than restated here, so an edge
    added later is covered by construction.
    """
    from atdd.coach.commands.issue_lifecycle import _NEXT_ACTION_HINTS

    config = {"gate": {"transitions": {"PLANNED->RED": True, "SMOKE->REFACTOR": True}}}
    lifecycle = _lifecycle(tmp_path, config)

    for phase, hint in _NEXT_ACTION_HINTS.items():
        if hint.to_phase is None:
            continue
        lifecycle._print_next_action(phase, ISSUE)
        out = capsys.readouterr().out
        edge = f"{phase}->{hint.to_phase}"
        expected = approval_required_for(config, phase, hint.to_phase)

        assert (f"--transition '{edge}'" in out) is expected, (
            f"the hint for {edge} {'omits' if expected else 'invents'} the "
            f"approval step the gate {'requires' if expected else 'does not require'}:\n{out}"
        )


def test_the_command_is_not_a_stored_string(tmp_path) -> None:
    """The regression guard: a rendered command in the table cannot know the config.

    #1750's defect was structural — the hint table held finished command lines,
    so no amount of config could change what it said. Keeping the EDGE as data
    and composing the command is what makes the two tests above possible.
    """
    from atdd.coach.commands.issue_lifecycle import _NEXT_ACTION_HINTS

    for phase, hint in _NEXT_ACTION_HINTS.items():
        for line in hint.lines:
            assert "atdd coach transition" not in line, (
                f"the {phase} hint stores a rendered transition command "
                f"({line!r}); it cannot reflect gate.transitions"
            )
