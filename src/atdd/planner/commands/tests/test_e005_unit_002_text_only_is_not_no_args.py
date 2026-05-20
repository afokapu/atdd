# URN: test:define-plans:atdd-plan:E005-UNIT-002-text-only-is-not-no-args
# Acceptance: acc:define-plans:E005-UNIT-002-text-only-is-not-no-args
# WMBT: wmbt:define-plans:E005
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E005-UNIT-002 — --text alone is a valid source and does not trigger the no-args guard."""
from __future__ import annotations

import pytest


def test_text_source_bypasses_no_args_guard():
    from atdd.planner.commands.plan import build_parser, classify_sources

    parser = build_parser()
    args = parser.parse_args(["--text", "x"])
    sources = classify_sources(args)

    assert len(sources) == 1, "Expected exactly one source from --text x"
    assert sources[0].type == "text"
    assert sources[0].value == "x"
