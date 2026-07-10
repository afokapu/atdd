# URN: component:govern-providers:orphan-detector-detection:backend:domain
# Runtime: python
# Purpose: Catch a bound implementation married to a convention_id no node declares
#          — a mechanism enforcing an obligation nobody wrote down — loudly, instead
#          of letting the runner default a nodeless bound rule silently to strict.
"""Orphan-detector detection (#1425 WMBT E002).

The binding lock is the MARRIAGE between an agnostic OBLIGATION (a convention node
under ``.atdd/extensions``) and a stack-specific MECHANISM (a workspace-provider
implementation). A ``bound`` entry whose ``convention_id`` matches NO convention
node is an ORPHAN: a detector enforcing an obligation nobody declared. The runner
tolerates it — :func:`atdd.enforce.conventions.rule_metadata` defaults a nodeless
rule to ``strict`` — so an orphan enforces silently rather than being caught.

Today four such phantom entries live in the real lock (``tester.*`` detectors with
no node). :func:`find_orphan_detectors` surfaces every one by name;
:func:`assert_no_orphan_detectors` turns that into a loud failure.

Only ``bound`` entries can be orphaned: a ``legacy-fallback`` entry declares no
implementation marriage, so a missing node for it is expected, not an orphan.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

_log = logging.getLogger(__name__)


class OrphanDetectorError(Exception):
    """A bound implementation is married to a convention_id no node declares."""


def _bound_convention_ids(substrate_home: str | Path) -> list[str]:
    """The ``convention_id`` of every ``disposition: bound`` entry in the lock.

    Returns ``[]`` when the lock is absent or malformed (there is nothing to
    orphan-check); a malformed lock is a wiring concern the runner surfaces
    separately, not an orphan verdict.
    """
    lock_path = Path(substrate_home) / ".atdd" / "binding.lock.yaml"
    if not lock_path.is_file():
        return []
    try:
        lock = yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        # An unreadable/malformed lock is a wiring concern surfaced elsewhere; the
        # orphan check has nothing to scan, but must not swallow the fault silently.
        _log.warning(
            "unreadable binding.lock.yaml — no orphan check possible",
            extra={"lock_path": str(lock_path), "error": str(exc)},
        )
        return []
    conventions = lock.get("conventions") if isinstance(lock, dict) else None
    conventions = conventions if isinstance(conventions, list) else []
    ids: list[str] = []
    for conv in conventions:
        if isinstance(conv, dict) and conv.get("disposition") == "bound":
            cid = conv.get("convention_id")
            if cid:
                ids.append(str(cid))
    return ids


def _convention_node_exists(substrate_home: str | Path, convention_id: str) -> bool:
    """Whether a ``<convention_id>.convention.yaml`` node is vendored under extensions.

    Mirrors :func:`atdd.enforce.conventions._convention_node_path` — resolution is
    keyed off the file name alone, so it is provider-agnostic.
    """
    ext_root = Path(substrate_home) / ".atdd" / "extensions"
    if not ext_root.is_dir():
        return False
    return any(ext_root.rglob(f"{convention_id}.convention.yaml"))


def find_orphan_detectors(substrate_home: str | Path) -> list[str]:
    """Every bound convention_id in the lock that no convention node declares.

    Sorted and de-duplicated. An empty list means the marriage is coherent — every
    bound implementation realizes an obligation that is actually written down.
    """
    orphans = {
        cid
        for cid in _bound_convention_ids(substrate_home)
        if not _convention_node_exists(substrate_home, cid)
    }
    return sorted(orphans)


def render_orphan_report(orphans: list[str]) -> str:
    """A loud, human-readable report naming each orphan binding (or a clean line)."""
    if not orphans:
        return "orphan-detectors: none — every bound implementation realizes a declared convention."
    lines = [
        f"orphan-detectors: {len(orphans)} bound implementation(s) married to a "
        f"convention no node declares:",
    ]
    for cid in orphans:
        lines.append(f"  [orphan] {cid} — bound in binding.lock.yaml, no <id>.convention.yaml node")
    return "\n".join(lines)


def assert_no_orphan_detectors(substrate_home: str | Path) -> list[str]:
    """Raise :class:`OrphanDetectorError` naming every orphan; else return ``[]``.

    The loud guard: a nodeless bound rule must be caught here, not left to default
    silently to ``strict`` in the runner.
    """
    orphans = find_orphan_detectors(substrate_home)
    if orphans:
        raise OrphanDetectorError(render_orphan_report(orphans))
    return orphans
