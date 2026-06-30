# URN: test:state-store:build-hook:version-projection
# Issue: #1172 (State Store owns version source-of-truth)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1172 — the build-time version projection (in-tree backend resolver).

Proves the stdlib-only resolver in ``build_meta_shim/_release_version.py``:
returns the store's release version when a store is present, and the explicit
``0.0.0+local`` fallback when absent — the novel no-store contract that keeps a
fresh-clone / pre-init build from failing. Loaded by path so the test does not
depend on setuptools (the backend module imports setuptools.build_meta).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from atdd.state.db import init_state_store
from atdd.state.store import ObjectStore, StateStore
from atdd.state.db import connect
from atdd.state import version as ver

_REPO_ROOT = Path(__file__).resolve().parents[4]
_RESOLVER_PATH = _REPO_ROOT / "build_meta_shim" / "_release_version.py"


def _load_resolver():
    spec = importlib.util.spec_from_file_location("_release_version_under_test", _RESOLVER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def resolver():
    return _load_resolver()


def _seed_store(control_root: Path) -> Path:
    return init_state_store(db_path=control_root / ".atdd" / "state" / "state.sqlite")


def test_resolver_returns_store_version_when_present(resolver, tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    _seed_store(root)
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(root))
    assert resolver.resolve_version() == "3.149.0"     # seeded baseline


def test_resolver_reflects_a_bump(resolver, tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    db = _seed_store(root)
    conn = connect(db)
    try:
        ver.bump(conn, "MINOR")                         # -> 3.150.0
    finally:
        conn.close()
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(root))
    assert resolver.resolve_version() == "3.150.0"


def test_resolver_falls_back_when_no_store(resolver, tmp_path, monkeypatch):
    empty = tmp_path / "fresh-clone"
    empty.mkdir()
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(empty))   # points at a store-less root
    assert resolver.resolve_version() == "0.0.0+local"
    assert resolver.LOCAL_FALLBACK_VERSION == ver.LOCAL_FALLBACK_VERSION


def test_resolver_falls_back_when_release_object_absent(resolver, tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    db = _seed_store(root)
    conn = connect(db)
    try:
        ObjectStore(conn).delete("release")             # store exists, no release object
    finally:
        conn.close()
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(root))
    assert resolver.resolve_version() == "0.0.0+local"


def test_resolver_walks_upward_from_cwd(resolver, tmp_path, monkeypatch):
    """No env override → resolve the nearest .atdd/state/state.sqlite at/above start."""
    root = tmp_path / "project"
    root.mkdir()
    _seed_store(root)
    child = root / "worktree" / "nested"
    child.mkdir(parents=True)
    monkeypatch.delenv("ATDD_CONTROL_ROOT", raising=False)
    assert resolver.resolve_version(start=child) == "3.149.0"


def test_fallback_is_pep440_local_version(resolver):
    # `0.0.0+local` must be a valid PEP 440 version (local segment) or setuptools
    # rejects it at build time.
    from packaging.version import Version  # setuptools vendors packaging; available in venv
    Version(resolver.LOCAL_FALLBACK_VERSION)
