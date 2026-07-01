# URN: test:govern-lifecycle:state:E058-SMOKE-001-publish-workflow-resolves-real-version-and-invokes-drain-double-gated
# Acceptance: acc:govern-lifecycle:E058-SMOKE-001-publish-workflow-resolves-real-version-and-invokes-drain-double-gated
# WMBT: wmbt:govern-lifecycle:E058
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E058-SMOKE-001 — the rewired publish pipeline resolves a real version + drains.

Dry-run proof (no PyPI, no network): drive the REAL ``atdd state version``
CLI over a tmp git repo carrying an annotated tag, exactly as the rewired
``publish.yml`` post-merge job does — reconcile the store's current from the
git tag, bump by the derived change class, and confirm the resolved version is
real (not the ``0.0.0+local`` skip) with a pending ``version_decided`` message a
drain would consume. Then lint ``publish.yml`` to confirm the wiring: reconcile
from ``git describe``, invoke the extension drain, the ``DRY_RUN`` /
``ATDD_RELEASE_ALLOW_PUBLISH`` double-gate, and the ``git describe --exact-match``
idempotency skip — and that the old ``0.0.0+local`` publish-skip is gone.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.state.cli import run
from atdd.state.db import connect
from atdd.state.store import StateStore
from atdd.state import version as ver

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PUBLISH_YML = _REPO_ROOT / ".github" / "workflows" / "publish.yml"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture()
def tagged_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat(atdd): wire release worker")
    _git(repo, "tag", "-a", "v3.151.0", "-m", "Release v3.151.0")
    return repo


def test_real_cli_reconcile_bump_resolves_real_version(tagged_repo, capsys, monkeypatch):
    """The real reconcile->bump->emit CLI sequence yields a real version."""
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tagged_repo))
    latest = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=tagged_repo, check=True, capture_output=True, text=True,
    ).stdout.strip()
    current = latest[1:] if latest.startswith("v") else latest
    subject = subprocess.run(
        ["git", "log", "-1", "--format=%B"],
        cwd=tagged_repo, check=True, capture_output=True, text=True,
    ).stdout.strip()
    change_class = ver.change_class_for_commit(subject)      # feat -> MINOR

    assert run(["init"]) == 0
    assert run(["version", "set", current]) == 0
    assert run(["version", "bump", "--class", change_class]) == 0
    capsys.readouterr()                                       # drain prior output
    assert run(["version", "emit"]) == 0
    resolved = capsys.readouterr().out.strip()

    assert resolved == "3.152.0"                              # MINOR over 3.151.0
    assert resolved != ver.LOCAL_FALLBACK_VERSION             # NOT the skip fallback


def test_real_cli_leaves_pending_version_decided_a_drain_would_consume(tagged_repo, monkeypatch):
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tagged_repo))
    assert run(["init"]) == 0
    assert run(["version", "set", "3.151.0"]) == 0
    assert run(["version", "bump", "--class", "MINOR"]) == 0

    conn = connect(tagged_repo / ".atdd" / "state" / "state.sqlite")
    try:
        pending = StateStore(conn).sync.pending_outbox()
    finally:
        conn.close()
    assert len(pending) == 1
    assert pending[0].operation == "version_decided"
    assert pending[0].payload["version"] == "3.152.0"


def test_publish_workflow_wires_reconcile_bump_drain_double_gated_idempotent():
    text = _PUBLISH_YML.read_text()
    # Reconcile the current from git tags (option b — CI-resolvable version).
    assert "git describe --tags" in text
    assert "atdd state version set" in text and "atdd state version bump" in text
    # Invoke the release-extension drain (replaces the skip).
    assert "drain_version_decided" in text
    # Double-gate: workflow DRY_RUN flag + the extension's env guard.
    assert "DRY_RUN" in text and "ATDD_RELEASE_ALLOW_PUBLISH" in text
    # Idempotency: an already-released HEAD is skipped.
    assert "git describe --exact-match" in text
    # The old 0.0.0+local publish-skip path is gone (no longer the terminal outcome).
    assert "publishable=false" not in text
