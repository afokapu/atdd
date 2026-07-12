"""Project the State Store back into ``.atdd/manifest.yaml`` (#1203 Phase 2).

Phase 2 makes the State Store **authoritative** for the work-item lifecycle and
demotes the manifest to a generated **projection**: the store is the source of
truth, and ``manifest.yaml`` is regenerated deterministically from the
``work_item`` objects so existing manifest readers keep working without drift.

A work item is keyed in the store by its **slug** (uid), its lifecycle phase is
the object ``state``, and every other field lives in the JSON ``data`` bag; the
GitHub issue number is the authoritative ``github`` external_ref (and mirrored in
``data`` for read-compat). This module rebuilds a manifest ``sessions`` entry
from each of those — the inverse of :mod:`atdd.state.manifest_import` — while
preserving non-work-item top-level keys (``version`` / ``created``).

Determinism: sessions are sorted by issue number then slug, and each entry's keys
are emitted in a fixed canonical order, so re-projecting an unchanged store
yields byte-identical YAML (no merge churn). Dependency discipline: stdlib +
``atdd.state`` + PyYAML (a core dep, as in the importer) — no ``atdd.coach.*``.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from atdd.state.db import connect, init_state_store
from atdd.state.paths import ATDD_DIR, resolve_control_root
from atdd.state.projections import work_item_projection

_log = logging.getLogger(__name__)

GITHUB_PROVIDER = "github"
_IDENTITY_KEY = "slug"
_STATE_KEY = "status"
_ISSUE_KEY = "issue_number"
#: Canonical manifest top-level keys preserved across a projection.
_DEFAULT_VERSION = "2.0"
#: Fixed session-key emission order (matches the hand-authored manifest); any key
#: not listed here is appended in sorted order so new fields stay deterministic.
_CANONICAL_SESSION_KEYS = (
    "id", "slug", "file", "issue_number", "type", "status",
    "created", "archived", "train", "branch", "feature", "wagon", "worktree",
)


def _manifest_path(control_root: Path) -> Path:
    return control_root / ATDD_DIR / "manifest.yaml"


def _ordered_session(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Re-key a session dict into the canonical order (deterministic emission)."""
    ordered: Dict[str, Any] = {}
    for key in _CANONICAL_SESSION_KEYS:
        if key in entry:
            ordered[key] = entry[key]
    for key in sorted(k for k in entry if k not in _CANONICAL_SESSION_KEYS):
        ordered[key] = entry[key]
    return ordered


def build_sessions(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Reconstruct the manifest ``sessions`` list from the store (deterministic).

    Inverse of :func:`atdd.state.manifest_import.import_manifest`: each
    ``work_item`` becomes ``{**data, slug, status}`` with the GitHub issue number
    taken from the authoritative external_ref. Sorted by issue number then slug.
    """
    sessions: List[Dict[str, Any]] = []
    for row in work_item_projection(conn):
        entry: Dict[str, Any] = dict(row.data)
        entry[_IDENTITY_KEY] = row.uid
        entry[_STATE_KEY] = row.state
        ref = row.external.get(GITHUB_PROVIDER)
        if ref is not None:
            # external_ref is the authoritative projection of the issue number.
            try:
                entry[_ISSUE_KEY] = int(ref)
            except (TypeError, ValueError):
                entry[_ISSUE_KEY] = ref
        sessions.append(_ordered_session(entry))
    sessions.sort(key=lambda s: (s.get(_ISSUE_KEY) is None, s.get(_ISSUE_KEY) or 0, s.get(_IDENTITY_KEY) or ""))
    return sessions


def build_manifest_doc(
    conn: sqlite3.Connection, *, base_doc: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build the full manifest projection, preserving non-work-item top-level keys.

    ``base_doc`` (the existing manifest, if any) carries ``version`` / ``created``
    and any other top-level sections forward unchanged; only ``sessions`` is
    regenerated from the store.
    """
    doc: Dict[str, Any] = dict(base_doc or {})
    doc.setdefault("version", _DEFAULT_VERSION)
    doc["sessions"] = build_sessions(conn)
    return doc


def dump_manifest(doc: Dict[str, Any]) -> str:
    """Serialize a manifest doc to deterministic YAML (stable across re-projection)."""
    return yaml.dump(doc, default_flow_style=False, sort_keys=False)


def write_manifest_projection(
    control_root: Optional[Path] = None,
    *,
    db_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
) -> Path:
    """Regenerate ``.atdd/manifest.yaml`` from the store; return the manifest path.

    The existing manifest (if present) seeds the preserved top-level keys. The
    store is opened read-only here — callers that just mutated the store should
    pass the same ``control_root`` / ``db_path``.
    """
    if control_root is not None:
        root: Optional[Path] = Path(control_root)
    elif manifest_path is not None:
        root = Path(manifest_path).resolve().parent.parent
    else:
        root = resolve_control_root(Path.cwd()).control_root

    manifest = Path(manifest_path) if manifest_path is not None else _manifest_path(root)
    store_db = init_state_store(db_path=db_path) if db_path is not None else init_state_store(start=root)

    base_doc: Optional[Dict[str, Any]] = None
    if manifest.is_file():
        base_doc = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}

    conn = connect(store_db)
    try:
        doc = build_manifest_doc(conn, base_doc=base_doc)
    finally:
        conn.close()

    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(dump_manifest(doc), encoding="utf-8")
    _log.info(
        "manifest regenerated as a State Store projection",
        extra={"manifest": str(manifest), "sessions": len(doc.get("sessions") or []), "db": str(store_db)},
    )
    return manifest
