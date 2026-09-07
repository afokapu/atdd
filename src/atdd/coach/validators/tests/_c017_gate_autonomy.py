# URN: component:govern-lifecycle:enforcing-phase-transition-gate:c017_gate_autonomy:backend:unit
# Runtime: python
# Purpose: Resolve gate.transitions against the autonomy each phase declares (#1798).

"""Shared resolver for the C017 acceptances.

``gate.transitions`` (``.atdd/config.yaml``) and ``autonomy``
(``phase_machine.convention.yaml``) are separate files that describe the same
thing from two directions: which edges stop on a human. Nothing compares them, so
they can disagree silently — and today they do, on ``SMOKE->REFACTOR``.

Pure: callers supply both mappings, so the unit acceptance can drive synthetic
tables and the smoke acceptance can drive the repository's real ones.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping

import yaml

from atdd.coach.utils.repo import find_repo_root

#: The repo's gate configuration, relative to the repo root.
CONFIG_REL = Path(".atdd/config.yaml")


def gate_transitions(repo_root: Path | None = None) -> Dict[str, Any]:
    """The ``gate.transitions`` mapping as committed, or ``{}`` when absent."""
    root = repo_root or find_repo_root()
    data = yaml.safe_load((root / CONFIG_REL).read_text()) or {}
    gate = data.get("gate") or {}
    return (gate.get("transitions") or {}) if isinstance(gate, Mapping) else {}


def operator_gated_agent_edges(
    phases: Mapping[str, Any], transitions: Mapping[str, Any]
) -> List[str]:
    """Gated edges whose FROM phase declares ``autonomy: agent``.

    An edge is only a violation when the config actually gates it (a falsey entry
    is an explicit ungating, not a gate) AND the machine says the persona may
    submit it. An edge whose phase declares ``operator`` is the convention working
    as intended, not a finding.
    """
    found: List[str] = []
    for edge, gated in (transitions or {}).items():
        if not gated:
            continue
        from_phase = str(edge).split("->", 1)[0].strip()
        spec = (phases or {}).get(from_phase) or {}
        if spec.get("autonomy") == "agent":
            found.append(str(edge))
    return sorted(found)
