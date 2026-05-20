# URN: test:define-plans:atdd-plan:D001-UNIT-001-help-lists-allowed-flags
# Acceptance: acc:define-plans:D001-UNIT-001-help-lists-allowed-flags
# WMBT: wmbt:define-plans:D001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""D001-UNIT-001 — atdd plan --help lists only the allowed flags.

Confirms the argparse surface ships with exactly the PLAN-1 flags and
none of the forbidden ones (--land, --prefix, --skip-validate).
"""
from __future__ import annotations

import pytest


def test_help_contains_required_flags():
    from atdd.planner.commands.plan import build_parser

    parser = build_parser()
    help_text = parser.format_help()

    for flag in ("--text", "--brief-out", "--json", "--quiet"):
        assert flag in help_text, f"Expected flag {flag!r} missing from --help"


def test_help_does_not_contain_forbidden_flags():
    from atdd.planner.commands.plan import build_parser

    parser = build_parser()
    help_text = parser.format_help()

    for flag in ("--land", "--prefix", "--skip-validate"):
        assert flag not in help_text, f"Forbidden flag {flag!r} found in --help"
