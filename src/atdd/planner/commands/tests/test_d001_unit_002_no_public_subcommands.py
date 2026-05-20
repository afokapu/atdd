# URN: test:define-plans:atdd-plan:D001-UNIT-002-no-public-subcommands
# Acceptance: acc:define-plans:D001-UNIT-002-no-public-subcommands
# WMBT: wmbt:define-plans:D001
# Phase: RED
# Layer: unit
# Assertion: structural
"""D001-UNIT-002 — atdd plan has no public subcommands."""
from __future__ import annotations

import argparse

import pytest


def test_parser_has_no_subparsers():
    from atdd.planner.commands.plan import build_parser

    parser = build_parser()

    subparser_actions = [
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    ]
    assert not subparser_actions, (
        "atdd plan must not register public subcommands; "
        f"found subparser actions: {subparser_actions}"
    )
