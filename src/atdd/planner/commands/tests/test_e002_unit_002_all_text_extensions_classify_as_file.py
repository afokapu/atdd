# URN: test:define-plans:atdd-plan:E002-UNIT-002-all-text-extensions-classify-as-file
# Acceptance: acc:define-plans:E002-UNIT-002-all-text-extensions-classify-as-file
# WMBT: wmbt:define-plans:E002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E002-UNIT-002 — all five text-file extensions yield type=file."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize("path", ["a.md", "b.txt", "c.yaml", "d.yml", "e.json"])
def test_text_extension_classifies_as_file(path):
    from atdd.planner.commands.plan import build_parser, classify_sources

    parser = build_parser()
    args = parser.parse_args([path])
    sources = classify_sources(args)

    assert len(sources) == 1
    assert sources[0].type == "file", (
        f"Expected type='file' for {path!r}, got {sources[0].type!r}"
    )
