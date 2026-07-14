# URN: component:migrate-projection-authority:test-support:migration_helpers:backend:tests
# Runtime: python
# Purpose: Hermetic manifest + State Store fixtures shared by the migrate-projection-authority acceptances.

"""Shared, hermetic fixtures for the migrate-projection-authority acceptances (#1400).

Every unit acceptance in this wagon needs some combination of the same three things: a legacy
manifest to migrate, an ephemeral store that touches no developer SQLite, and a repo root that
looks like a real Control Root without being one anybody cares about. None of these reach the
network or a provider — the migration is provider-free by construction (I7), and these helpers
keep the tests that prove it provider-free too.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import yaml

from .._fixtures import (  # re-exported: the acceptances import these from this module
    control_root,
    memory_store,
)

#: Literal uids, not minted ones. A test that asserts "the file is named by the uid" must know the
#: uid before it runs, or it is asserting that the tool agrees with itself.
UID_A = "wi_01HF7YAT00M78607F000000001"
UID_B = "wi_01HF7YAT00M78607F000000002"
UID_C = "wi_01HF7YAT00M78607F000000003"


def entry(
    slug: str,
    *,
    uid: Optional[str] = None,
    phase: str = "PLANNED",
    issue_number: Optional[int] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """One legacy manifest ``sessions`` entry."""
    row: Dict[str, Any] = {"id": slug, "slug": slug, "status": phase, "type": "implementation"}
    if uid is not None:
        row["uid"] = uid
    if issue_number is not None:
        row["issue_number"] = issue_number
    row.update(extra)
    return row


def write_manifest(root: Path, sessions: Sequence[Dict[str, Any]]) -> Path:
    """Write a legacy ``.atdd/manifest.yaml`` into ``root``; return its path."""
    path = Path(root) / ".atdd" / "manifest.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"version": "2.0", "sessions": list(sessions)},
            default_flow_style=False, sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def read_manifest(root: Path) -> Dict[str, Any]:
    """Read back the legacy manifest (to assert what a minting run recorded in it)."""
    return yaml.safe_load((Path(root) / ".atdd" / "manifest.yaml").read_text(encoding="utf-8")) or {}


def healthy_sessions() -> List[Dict[str, Any]]:
    """Three well-formed entries — a uid, a slug, a phase, and a GitHub issue number each."""
    return [
        entry("alpha", uid=UID_A, phase="PLANNED", issue_number=11),
        entry("beta", uid=UID_B, phase="GREEN", issue_number=12),
        entry("gamma", uid=UID_C, phase="INIT", issue_number=13),
    ]


def projection_files(root: Path, out_dir: Optional[Path] = None) -> List[str]:
    """The projection filenames under ``root`` (or ``out_dir``), sorted. ``[]`` when there are none."""
    directory = Path(out_dir) if out_dir is not None else Path(root) / ".atdd" / "state" / "projection"
    if not directory.is_dir():
        return []
    return sorted(path.name for path in directory.glob("*.yaml"))
