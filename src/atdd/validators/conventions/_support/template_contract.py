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

    def evaluate(self, graph, config=None) -> List[dict]:
        """Execute this template's graph question against ``graph`` and return
        failure-evidence records.

        The real composed graph is the canonical execution substrate; ``config``
        parameterizes the template for a specific variant. Selector -> traversal
        -> invariant -> evidence is implemented per template_id in
        ``_support.evaluators``. Each evidence dict's keys are a subset of
        ``failure_evidence`` (the template contract).
        """
        from .evaluators import evaluate as _evaluate

        return _evaluate(self.template_id, graph, config)


def field_names() -> List[str]:
    return [f.name for f in fields(TemplateContract)]
