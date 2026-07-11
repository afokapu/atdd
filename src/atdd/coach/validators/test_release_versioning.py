"""
Release versioning validation (#1172 State Store SoT model).

Post-#1172 the authoritative release version lives in the **State Store**
singleton ``release`` object, not a static ``version = "..."`` line in
``pyproject.toml`` (now ``dynamic = ["version"]``, resolved by the in-tree build
backend from the store). ``IssueManager._verify_release_gate`` — the release
gate on the COMPLETE transition — therefore reads the store version via
``atdd.state.version.emit`` (non-raising: real version, or the local fallback
``0.0.0+local`` when none is set).

These tests pin that behavior AND carry the RED discriminator for the #1172
follow-up fix: a **dynamic** ``pyproject.toml`` (no static ``version =`` line)
plus a store that HAS a version — where the OLD pyproject-parsing gate returned
``(False, "could not parse version")`` and the NEW store-reading gate returns
``(True, ...)``.
"""

import pytest

from atdd.coach.commands.issue import IssueManager
from atdd.state.db import connect, init_state_store
from atdd.state.store import ObjectStore
from atdd.state import version as ver


pytestmark = pytest.mark.platform


# A dynamic pyproject.toml as it exists post-#1172: NO static ``version =`` line;
# the version is an ``attr`` resolved from the build backend at build time. The
# OLD gate's ``_read_version_from_file`` regex finds nothing here.
DYNAMIC_PYPROJECT = """\
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "atdd_version_backend"
backend-path = ["build_meta_shim"]

[project]
name = "atdd"
dynamic = ["version"]

[tool.setuptools.dynamic]
version = {attr = "atdd_version_backend.VERSION"}
"""

RELEASE_CONFIG = """\
release:
  version_file: pyproject.toml
  tag_prefix: v
"""


def _make_repo(tmp_path, *, config: str = RELEASE_CONFIG, pyproject: str = DYNAMIC_PYPROJECT):
    """A hermetic repo dir with a dynamic pyproject + an initialized State Store.

    The ``.atdd/config.yaml`` marker makes ``tmp_path`` a Control Root, so the
    gate's ``init_state_store(start=self.target_dir)`` resolves the store to
    ``tmp_path/.atdd/state/state.sqlite``. Returns ``(IssueManager, store_path)``.
    """
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (atdd_dir / "config.yaml").write_text(config)
    (tmp_path / "pyproject.toml").write_text(pyproject)
    db = init_state_store(db_path=atdd_dir / "state" / "state.sqlite")
    return IssueManager(target_dir=tmp_path), db


@pytest.fixture(autouse=True)
def _no_control_root_env(monkeypatch):
    """Hermetic store resolution: never let an interim ATDD_CONTROL_ROOT override
    (the #1315 workaround) redirect the gate's store lookup away from tmp_path."""
    monkeypatch.delenv("ATDD_CONTROL_ROOT", raising=False)


# --------------------------------------------------------------------------- #
# SPEC-RELEASE-0001: PASS when the State Store holds a real release version.
# --------------------------------------------------------------------------- #
def test_release_gate_passes_when_store_has_version(tmp_path):
    """A store with a real release version passes the gate — even with a dynamic
    pyproject that has NO static ``version =`` line."""
    manager, db = _make_repo(tmp_path)
    conn = connect(db)
    try:
        ver.set_version(conn, "1.2.3")
    finally:
        conn.close()

    passed, messages = manager._verify_release_gate(force=False)

    assert passed, "\n".join(messages)
    assert any("1.2.3" in m and "State Store SoT" in m for m in messages), messages


# --------------------------------------------------------------------------- #
# SPEC-RELEASE-0002: RED discriminator — dynamic pyproject + store WITH version.
# OLD gate: (False, "could not parse version"). NEW gate: (True, ...).
# --------------------------------------------------------------------------- #
def test_release_gate_dynamic_pyproject_reads_store_not_file(tmp_path):
    """The exact #1172 regression: a dynamic pyproject (no static version) blocked
    every COMPLETE under the OLD gate. The store holds the version → NEW passes."""
    manager, db = _make_repo(tmp_path)
    conn = connect(db)
    try:
        ver.set_version(conn, "3.149.0")
        # Pin the OLD failure mode: the dynamic pyproject genuinely carries no
        # static ``version =`` line, so file-parsing has nothing to read.
        import re
        assert not re.search(
            r'(?m)^\s*version\s*=\s*["\']', (tmp_path / "pyproject.toml").read_text()
        ), "fixture pyproject must be dynamic (no static version line)"
    finally:
        conn.close()

    passed, messages = manager._verify_release_gate(force=False)

    assert passed, "\n".join(messages)
    assert not any("could not parse version" in m for m in messages), messages


# --------------------------------------------------------------------------- #
# SPEC-RELEASE-0003: FAIL when only the local fallback is resolvable.
# --------------------------------------------------------------------------- #
def test_release_gate_fails_on_local_fallback(tmp_path):
    """No release object in the store → ``emit`` returns the local fallback →
    the gate correctly blocks and points at ``atdd state version bump``."""
    manager, db = _make_repo(tmp_path)
    conn = connect(db)
    try:
        ObjectStore(conn).delete(ver.RELEASE_UID)  # remove the migration-v2 seed
        assert ver.emit(conn) == ver.LOCAL_FALLBACK_VERSION
    finally:
        conn.close()

    passed, messages = manager._verify_release_gate(force=False)

    assert not passed, "\n".join(messages)
    assert any(ver.LOCAL_FALLBACK_VERSION in m for m in messages), messages
    assert any("version bump" in m for m in messages), messages


# --------------------------------------------------------------------------- #
# SPEC-RELEASE-0004: early SKIPPED paths preserved.
# --------------------------------------------------------------------------- #
def test_release_gate_skipped_on_force(tmp_path):
    manager, _ = _make_repo(tmp_path)
    passed, messages = manager._verify_release_gate(force=True)
    assert passed
    assert any("SKIPPED (--force)" in m for m in messages), messages


def test_release_gate_skipped_without_config(tmp_path):
    manager = IssueManager(target_dir=tmp_path)  # no .atdd/config.yaml at all
    passed, messages = manager._verify_release_gate(force=False)
    assert passed
    assert any("no .atdd/config.yaml" in m for m in messages), messages


def test_release_gate_skipped_without_release_config(tmp_path):
    manager, _ = _make_repo(tmp_path, config="code:\n  toolkit: src/atdd\n")
    passed, messages = manager._verify_release_gate(force=False)
    assert passed
    assert any("no release config" in m for m in messages), messages
