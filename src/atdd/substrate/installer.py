"""Substrate installer: versioned install home + sha256 digest + lockfile (WMBT E001).

Installs a validated package into a content-addressed, versioned home under
`.atdd/` and records it in `.atdd/substrate.lock.yaml`. Core loads substrate from
the lockfile — `atdd list` renders it without scanning the filesystem.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import yaml

from atdd.substrate import schemas

LOCK_FILE = "substrate.lock.yaml"
SUBSTRATE_FILE = "substrate.yaml"
LOCK_SCHEMA_VERSION = "1.0.0"

# package kind → install subdirectory under .atdd/
_KIND_DIR = {"extension": "extensions", "workspace": "workspaces"}

# Generated artifacts a python run DEPOSITS into a tree — never package source.
# They are not authored, not shipped and not installed; they appear only because
# something executed inside the tree (e.g. `atdd enforce` subprocessing the
# vendored pytest provider). The digest content-addresses SOURCE, so every walk
# of it — the producer's here and the enforce substrate guard's verifier — must
# see the same source-only file set. Digesting bytecode instead made a plain
# `atdd enforce` run turn a pristine vendored tree into a false [TAMPERED] (#1603).
#
# Kept as narrow as the generators allow, because an excluded file is a file
# tamper detection cannot see. `__pycache__/` is deliberately NOT excluded by
# NAME — CPython writes only `.pyc` into it, so the suffix rule already covers
# every real cache file, and anything ELSE planted under that name (a `.py`
# payload hiding behind a directory the guard "ignores") stays digested and
# still trips the guard. `.pytest_cache/` has no such stable file grammar (json,
# CACHEDIR.TAG, .gitignore, lastfailed…), so it is excluded by directory name.
_GENERATED_DIR_NAMES = frozenset({".pytest_cache"})
_GENERATED_SUFFIXES = frozenset({".pyc", ".pyo"})


def install_path(project_root: str | Path, kind: str, package_id: str, version: str) -> Path:
    """The versioned install home: `.atdd/{extensions,workspaces}/<id>/<version>/`."""
    sub = _KIND_DIR.get(kind)
    if sub is None:
        raise ValueError(f"cannot install kind {kind!r}")
    return Path(project_root) / ".atdd" / sub / package_id / version


def iter_digest_files(package_dir: str | Path) -> list[Path]:
    """Every SOURCE file under *package_dir*, sorted; generated caches excluded.

    The single definition of "what the content digest covers", shared by the
    producer (`compute_digest`) and the verifier
    (`atdd.enforce.substrate_guard`). Excluding a file here hides it from tamper
    detection, so the exclusion set is deliberately narrow: compiled bytecode and
    pytest's cache dir only. Any authored file — `.py`, `.yaml`, anything else —
    still lands in the digest and a change to it is still caught.
    """
    root = Path(package_dir)
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix not in _GENERATED_SUFFIXES
        and _GENERATED_DIR_NAMES.isdisjoint(p.relative_to(root).parts)
    )


def compute_digest(package_dir: str | Path) -> str:
    """Content-address a package: sha256 over sorted (relpath, bytes). Stable."""
    root = Path(package_dir)
    h = hashlib.sha256()
    for f in iter_digest_files(root):
        rel = f.relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


def install(
    package_dir: str | Path,
    project_root: str | Path,
    *,
    kind: str,
    package_id: str,
    version: str,
) -> Path:
    """Copy the package into its versioned home (idempotent). Returns the path."""
    dest = install_path(project_root, kind, package_id, version)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(package_dir, dest)
    return dest


def read_lock(project_root: str | Path) -> dict:
    """Load `.atdd/substrate.lock.yaml` (schema-validated), or an empty lock."""
    path = Path(project_root) / ".atdd" / LOCK_FILE
    if not path.exists():
        return {"schema_version": LOCK_SCHEMA_VERSION, "artifacts": []}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    schemas.validate_lock(data, source=path)
    return data


def write_lock(project_root: str | Path, lock: dict) -> None:
    """Validate then atomically write `.atdd/substrate.lock.yaml`."""
    schemas.validate_lock(lock, source="<substrate.lock.yaml>")
    path = Path(project_root) / ".atdd" / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    tmp.replace(path)


def upsert_lock_entry(project_root: str | Path, entry: dict) -> dict:
    """Add or replace a lock entry by id (idempotent), returning the new lock."""
    lock = read_lock(project_root)
    arts = [a for a in lock.get("artifacts", []) if a.get("id") != entry["id"]]
    arts.append(entry)
    arts.sort(key=lambda a: a["id"])
    lock["artifacts"] = arts
    lock.setdefault("schema_version", LOCK_SCHEMA_VERSION)
    write_lock(project_root, lock)
    return lock


def remove_lock_entry(project_root: str | Path, package_id: str) -> dict:
    """Drop a lock entry by id, returning the new lock."""
    lock = read_lock(project_root)
    lock["artifacts"] = [a for a in lock.get("artifacts", []) if a.get("id") != package_id]
    write_lock(project_root, lock)
    return lock


def list_substrate(project_root: str | Path) -> list[dict]:
    """The installed substrate, read from the lockfile (no filesystem scan)."""
    return read_lock(project_root).get("artifacts", [])
