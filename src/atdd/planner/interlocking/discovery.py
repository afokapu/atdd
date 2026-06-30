# URN: component:plan:train-interlocking:Discovery:backend:application
# Runtime: python
# Purpose: Locate train-interlocking artifacts under their canonical home (#1249).
"""Discover the train-interlocking artifacts a repo declares.

The canonical home (issue #1248 / parent #1246) is
``plan/_trains/_interlockings/<id>.yaml`` with a thin discovery index at
``plan/_trains/_interlockings.yaml``. This module is the single place planner
validators and the convention archetypes ask "which interlockings exist, and
where do they live?" so the home rule is asserted in exactly one place.

Stdlib + yaml only; no IO beyond reading the registry file.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import yaml

__all__ = [
    "INTERLOCKINGS_HOME",
    "INTERLOCKINGS_REGISTRY",
    "interlocking_home",
    "interlocking_registry_path",
    "iter_interlocking_paths",
    "registry_entries",
]

INTERLOCKINGS_HOME = "plan/_trains/_interlockings"
INTERLOCKINGS_REGISTRY = "plan/_trains/_interlockings.yaml"


def interlocking_home(root: Path | str) -> Path:
    return Path(root) / INTERLOCKINGS_HOME


def interlocking_registry_path(root: Path | str) -> Path:
    return Path(root) / INTERLOCKINGS_REGISTRY


def iter_interlocking_paths(root: Path | str) -> List[Path]:
    """Return every interlocking artifact file under the canonical home.

    A top-level ``*.yaml`` directly under ``_interlockings/`` is an artifact; the
    per-id projection subdirectories (``<id>/coverage.yaml`` etc.) are derived
    outputs and are NOT artifacts, so only the immediate children are returned.
    Returns ``[]`` when the home does not exist (a repo may declare no
    interlockings).
    """
    home = interlocking_home(root)
    if not home.is_dir():
        return []
    return sorted(p for p in home.glob("*.yaml") if p.is_file())


def registry_entries(root: Path | str) -> Tuple[dict, ...]:
    """Return the declared registry entries (empty tuple when absent/malformed)."""
    path = interlocking_registry_path(root)
    if not path.is_file():
        return ()
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return ()
    entries = doc.get("interlockings") or []
    return tuple(e for e in entries if isinstance(e, dict))
