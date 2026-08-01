"""Resolving which bound conventions a run enforces.

Split out of :mod:`atdd.enforce.runner`, which had accumulated the lock read, the
disposition filter and the rule selection alongside provider invocation and verdict
judging. Reading the binding lock and choosing a subset of it are separate concerns
from running detectors, and they change for separate reasons.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml


def load_bound(substrate_home: Path, error_cls) -> list:
    """Every convention entry in the binding lock whose disposition is ``bound``.

    A missing lock is an empty substrate, not a fault — the caller reports the
    clean no-op. A malformed lock IS a fault: it cannot be distinguished from an
    empty one by inspection, and guessing would silently enforce nothing.
    """
    lock_path = substrate_home / ".atdd" / "binding.lock.yaml"
    lock: dict = {}
    if lock_path.is_file():
        try:
            lock = yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise error_cls(f"malformed binding.lock.yaml: {exc}") from exc

    conventions = lock.get("conventions") if isinstance(lock, dict) else None
    conventions = conventions if isinstance(conventions, list) else []
    return [c for c in conventions if isinstance(c, dict) and c.get("disposition") == "bound"]


def select(bound: list, rules: Optional[set], error_cls) -> list:
    """Narrow ``bound`` to ``rules``, refusing a selection that names an unknown rule.

    ``rules`` is a SELECTION, not a filter: every named rule must resolve or this
    raises. Silently dropping an unknown id would leave the caller running fewer
    detectors than it asked for — and a selection resolving to nothing spawns no
    provider at all, which reports CLEAN. A mistyped rule id would then turn a gate
    into a rubber stamp, so an unresolvable selection is a usage error (the same
    fail-closed stance the runner takes on a crashed provider).
    """
    if rules is None:
        return bound

    known = {str(c.get("convention_id")) for c in bound}
    unknown = sorted(set(rules) - known)
    if unknown:
        # Name ONLY the unresolvable ids — listing the resolvable ones back would
        # bury the typo in noise on a repo with dozens of bound rules.
        raise error_cls("rule selection names no bound convention: " + ", ".join(unknown))

    # Lock order, not selection order: the run is reproducible regardless of how the
    # caller spelled the set.
    return [c for c in bound if str(c.get("convention_id")) in rules]
