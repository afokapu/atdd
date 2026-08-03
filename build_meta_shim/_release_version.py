"""Stdlib-only release-version resolver for the in-tree build backend (#1172).

Kept separate from :mod:`atdd_version_backend` (which imports
``setuptools.build_meta``) so the resolution logic is importable and testable
**without** setuptools — and so it never imports ``atdd`` (this runs under build
isolation). It re-implements a minimal Control-Root resolver rather than reusing
:mod:`atdd.state.paths`.

Local-first with an explicit no-store fallback: a build over a fresh clone / CI
before ``atdd state init`` emits :data:`LOCAL_FALLBACK_VERSION` rather than
failing. Never raises — any error degrades to the fallback.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import List, Optional

#: Deterministic version when no store version is resolvable (PEP 440 local
#: segment). MUST match ``atdd.state.version.LOCAL_FALLBACK_VERSION``.
LOCAL_FALLBACK_VERSION = "0.0.0+local"

_ATDD_DIR = ".atdd"
_STATE_STORE_RELATIVE = Path(_ATDD_DIR) / "state" / "state.sqlite"
_CONTROL_ROOT_ENV = "ATDD_CONTROL_ROOT"
_RELEASE_UID = "release"


def _candidate_store_paths(start: Path) -> List[Path]:
    """Store paths to try, most-specific first.

    An explicit ``ATDD_CONTROL_ROOT`` is AUTHORITATIVE: if it carries no store,
    there is no store, and the caller gets :data:`LOCAL_FALLBACK_VERSION`. It must
    NOT degrade into the upward walk — that walk escapes the named root and, under
    the single shared Control Root (#1346), reaches an *ancestor's* store, which
    would project a foreign project's release version into this build.
    """
    override = os.environ.get(_CONTROL_ROOT_ENV)
    if override:
        return [Path(override).expanduser() / _STATE_STORE_RELATIVE]
    start = start.resolve()
    return [directory / _STATE_STORE_RELATIVE for directory in (start, *start.parents)]


def _resolve_store_path(start: Optional[Path] = None) -> Optional[Path]:
    start = Path.cwd() if start is None else Path(start)
    for path in _candidate_store_paths(start):
        if path.is_file():
            return path
    return None


def resolve_version(start: Optional[Path] = None) -> str:
    """Return the store's release version, or :data:`LOCAL_FALLBACK_VERSION`.

    Never raises: any resolution / read error degrades to the fallback so the
    build always succeeds (a broken or absent store must not break packaging).
    """
    path = _resolve_store_path(start)
    if path is None:
        return LOCAL_FALLBACK_VERSION
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT data FROM objects WHERE uid=? AND kind='release'",
                (_RELEASE_UID,),
            ).fetchone()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        return LOCAL_FALLBACK_VERSION
    if not row or not row[0]:
        return LOCAL_FALLBACK_VERSION
    try:
        version = json.loads(row[0]).get("version")
    except (ValueError, TypeError):
        return LOCAL_FALLBACK_VERSION
    return str(version) if version else LOCAL_FALLBACK_VERSION
