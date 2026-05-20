# URN: test:define-plans:atdd-plan:E001-UNIT-001-text-flag-yields-text-source
# Acceptance: acc:define-plans:E001-UNIT-001-text-flag-yields-text-source
# WMBT: wmbt:define-plans:E001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E001-UNIT-001 — --text produces a text SourceItem with the raw string."""
from __future__ import annotations

import pytest


def test_text_flag_produces_text_source_item():
    from atdd.planner.commands.plan import build_parser, classify_sources

    parser = build_parser()
    args = parser.parse_args(["--text", "hello world"])
    sources = classify_sources(args)

    assert len(sources) == 1
    assert sources[0].type == "text"
    assert sources[0].value == "hello world"


def test_text_flag_does_not_open_files(monkeypatch):
    """--text must not attempt any file I/O."""
    import builtins

    original_open = builtins.open

    def fail_open(path, *a, **kw):
        raise AssertionError(f"--text must not open files, but open({path!r}) was called")

    from atdd.planner.commands.plan import build_parser, classify_sources

    monkeypatch.setattr(builtins, "open", fail_open)
    parser = build_parser()
    args = parser.parse_args(["--text", "raw content"])
    sources = classify_sources(args)

    assert sources[0].type == "text"
