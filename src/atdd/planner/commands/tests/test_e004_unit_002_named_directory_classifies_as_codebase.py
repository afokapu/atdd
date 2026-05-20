# URN: test:define-plans:atdd-plan:E004-UNIT-002-named-directory-classifies-as-codebase
# Acceptance: acc:define-plans:E004-UNIT-002-named-directory-classifies-as-codebase
# WMBT: wmbt:define-plans:E004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E004-UNIT-002 — extensionless path classifies as codebase."""
from __future__ import annotations

import pytest


def test_extensionless_path_classifies_as_codebase():
    from atdd.planner.commands.plan import build_parser, classify_sources

    parser = build_parser()
    args = parser.parse_args(["src/myproject"])
    sources = classify_sources(args)

    assert len(sources) == 1
    assert sources[0].type == "codebase"
    assert sources[0].path == "src/myproject"
