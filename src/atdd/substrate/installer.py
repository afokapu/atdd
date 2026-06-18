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


def install_path(project_root: str | Path, kind: str, package_id: str, version: str) -> Path:
    """The versioned install home: `.atdd/{extensions,workspaces}/<id>/<version>/`."""
    sub = _KIND_DIR.get(kind)
    if sub is None:
        raise ValueError(f"cannot install kind {kind!r}")
    return Path(project_root) / ".atdd" / sub / package_id / version


def compute_digest(package_dir: str | Path) -> str:
    """Content-address a package: sha256 over sorted (relpath, bytes). Stable."""
    root = Path(package_dir)
    h = hashlib.sha256()
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
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
