# URN: test:define-plans:atdd-plan:E002-UNIT-001-md-classifies-as-file
# Acceptance: acc:define-plans:E002-UNIT-001-md-classifies-as-file
# WMBT: wmbt:define-plans:E002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E002-UNIT-001 — .md positional yields a file SourceItem."""
from __future__ import annotations

import pytest


def test_md_path_classifies_as_file():
    from atdd.planner.commands.plan import build_parser, classify_sources

    parser = build_parser()
    args = parser.parse_args(["docs/spec.md"])
    sources = classify_sources(args)

    assert len(sources) == 1
    assert sources[0].type == "file"
    assert sources[0].path == "docs/spec.md"
