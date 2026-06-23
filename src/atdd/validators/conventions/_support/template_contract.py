"""Typed contract for convention validator templates (#1204).

Every template exposed by a family ``archetype.py`` must carry these eight
mandatory metadata fields. ``REQUIRED_FIELDS`` is the introspectable source of
truth; ``TemplateContract`` is the concrete carrier.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import List

REQUIRED_FIELDS = [
    "family_id",
    "template_id",
    "question",
    "selector",
    "traversal",
    "invariant",
    "auto_capture",
    "failure_evidence",
]


@dataclass(frozen=True)
class TemplateContract:
    family_id: str
    template_id: str
    question: str
    selector: str
    traversal: str
    invariant: str
    auto_capture: str
    failure_evidence: List[str]


def field_names() -> List[str]:
    return [f.name for f in fields(TemplateContract)]
