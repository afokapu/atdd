# URN: test:define-plans:atdd-plan-session:Y002-UNIT-001-advance-step-choices-are-the-new-names
# Acceptance: acc:define-plans:Y002-UNIT-001-advance-step-choices-are-the-new-names
# WMBT: wmbt:define-plans:Y002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""Y002-UNIT-001 — `atdd plan advance --step` offers only the new stage names.

The `--step` choices derive from the `Step` enum, so this is the cheapest proof
that the rename reached the operator-visible CLI surface rather than stopping at
the enum literal. It also pins the consequence the issue does not spell out: a
retired stage name is now an argparse error, not a silently accepted value.

RED: the enum still spells the gates define/locate/prepare/confirm.
"""
from __future__ import annotations

import argparse

import pytest

from atdd.planner.commands.plan_session_cli import build_parser

NEW_STEPS = ["intent", "attach", "compose", "ratify", "authored"]
RETIRED_STEPS = ["define", "locate", "prepare", "confirm"]


def _advance_step_choices() -> list:
    """The `--step` choices argparse actually offers, read off the built parser."""
    parser = build_parser()
    subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    step = next(a for a in subs.choices["advance"]._actions if a.dest == "step")
    return list(step.choices)


def test_advance_step_choices_are_exactly_the_new_stage_names():
    assert _advance_step_choices() == NEW_STEPS


@pytest.mark.parametrize("step", NEW_STEPS)
def test_advance_accepts_every_new_stage_name(step):
    args = build_parser().parse_args(["advance", "--id", "s", "--step", step])
    assert args.step == step


@pytest.mark.parametrize("retired", RETIRED_STEPS)
def test_advance_refuses_a_retired_stage_name(retired):
    """A retired name fails loudly through argparse, which lists the valid
    choices — unlike a stale persisted value, which used to traceback."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["advance", "--id", "s", "--step", retired])
