"""Core's half of the documentation obligation.

Core owns the lifecycle obligation and nothing about documentation itself. What a
document IS — AsciiDoc, identity, ADRs, the relationship graph, rendering — belongs to
the installed capability (`atdd.extension.planner.docs`), reached over the
`atdd.documentation` entry point.

TWO HALVES, ONE CONTRACT. `declaration` decides what core can decide alone: a
declaration is well-formed, and its named artifacts are in the change set. `capability`
delegates everything else over the entry-point group. `should_delegate` is the hinge —
integrity runs first, and a caller that skips it hands the capability an unchecked
declaration, gets COULD_NOT_CHECK, and reports core's own omission as the extension's
blindness.

The two arrived on separate branches (#1797 and #1789) because an issue binds exactly
one feature. This module is where they become one surface.
"""
from __future__ import annotations

from . import verdict
from .capability import (
    ENTRY_POINT_GROUP,
    SEAM_RULE_ID,
    DocumentationCheck,
    Finding,
    judge_documentation,
    resolve_documentation_capability,
)
from .declaration import (
    KNOWN_IMPACTS,
    DeclarationCheck,
    check_declaration_integrity,
    should_delegate,
)

__all__ = [
    # the seam (#1789)
    "ENTRY_POINT_GROUP",
    "SEAM_RULE_ID",
    "DocumentationCheck",
    "Finding",
    "judge_documentation",
    "resolve_documentation_capability",
    "verdict",
    # the integrity gate (#1797)
    "KNOWN_IMPACTS",
    "DeclarationCheck",
    "check_declaration_integrity",
    "should_delegate",
]
