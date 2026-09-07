"""Core's half of the documentation obligation.

Core owns the lifecycle obligation and nothing about documentation itself. What a
document IS — AsciiDoc, identity, ADRs, the relationship graph, rendering — belongs to
the installed capability (`atdd.extension.planner.docs`), reached over the
`atdd.documentation` entry point.
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
__all__ = [
    "ENTRY_POINT_GROUP", "SEAM_RULE_ID",
    "DocumentationCheck", "Finding",
    "judge_documentation", "resolve_documentation_capability", "verdict",
]
