# URN: test:define-plans:atdd-plan:E001-UNIT-002-text-and-positional-combined
# Acceptance: acc:define-plans:E001-UNIT-002-text-and-positional-combined
# WMBT: wmbt:define-plans:E001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E001-UNIT-002 — combining --text with a positional yields two sources."""
from __future__ import annotations

import pytest


def test_text_and_file_positional_produce_two_sources():
    from atdd.planner.commands.plan import build_parser, classify_sources

    parser = build_parser()
    args = parser.parse_args(["docs/spec.md", "--text", "extra note"])
    sources = classify_sources(args)

    assert len(sources) == 2
    types = {s.type for s in sources}
    assert "file" in types
    assert "text" in types

    file_src = next(s for s in sources if s.type == "file")
    text_src = next(s for s in sources if s.type == "text")
    assert file_src.path == "docs/spec.md"
    assert text_src.value == "extra note"
