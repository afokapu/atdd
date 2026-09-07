"""Core's half of the documentation obligation.

Core owns the lifecycle obligation and nothing about documentation itself. What a
document IS — AsciiDoc, identity, ADRs, the relationship graph, rendering — belongs to
the installed capability (`atdd.extension.planner.docs`), reached over the
`atdd.documentation` entry point.
"""
from __future__ import annotations

from .declaration import (
    KNOWN_IMPACTS,
    DeclarationCheck,
    check_declaration_integrity,
    should_delegate,
)

__all__ = [
    "KNOWN_IMPACTS",
    "DeclarationCheck",
    "check_declaration_integrity",
    "should_delegate",
]
