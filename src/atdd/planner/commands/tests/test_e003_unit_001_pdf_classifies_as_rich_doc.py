# URN: test:define-plans:atdd-plan:E003-UNIT-001-pdf-classifies-as-rich-doc
# Acceptance: acc:define-plans:E003-UNIT-001-pdf-classifies-as-rich-doc
# WMBT: wmbt:define-plans:E003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E003-UNIT-001 — .pdf positional yields a rich_doc SourceItem with path captured."""
from __future__ import annotations

import pytest


def test_pdf_classifies_as_rich_doc():
    from atdd.planner.commands.plan import build_parser, classify_sources

    parser = build_parser()
    args = parser.parse_args(["docs/brief.pdf"])
    sources = classify_sources(args)

    assert len(sources) == 1
    assert sources[0].type == "rich_doc"
    assert sources[0].path == "docs/brief.pdf"
