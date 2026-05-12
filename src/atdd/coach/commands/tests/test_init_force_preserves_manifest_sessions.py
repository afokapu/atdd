"""Regression test for issue #580: `atdd init --force` wipes manifest sessions.

Bug: _create_manifest(force=True) always writes sessions=[] regardless of
existing content, silently dropping all registered session history.

Fix: When force=True and manifest already exists, preserve the sessions list
(same deep-merge approach used by _create_config).

Run:
    PYTHONPATH=src python3 -m pytest -q \
        src/atdd/coach/commands/tests/test_init_force_preserves_manifest_sessions.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.commands.initializer import ProjectInitializer

pytestmark = [pytest.mark.platform]


def _write_manifest(atdd_dir: Path, sessions: list) -> Path:
    atdd_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = atdd_dir / "manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump({
            "version": "2.0",
            "created": "2026-03-31",
            "sessions": sessions,
        }, default_flow_style=False, sort_keys=False)
    )
    return manifest_path


def test_force_init_preserves_existing_sessions(tmp_path):
    """--force must not wipe sessions: list from an existing manifest."""
    sessions = [
        {"id": "42", "slug": "some-feature", "issue_number": 42, "status": "GREEN"},
        {"id": "99", "slug": "another-fix", "issue_number": 99, "status": "SMOKE"},
    ]
    manifest_path = _write_manifest(tmp_path / ".atdd", sessions)

    initializer = ProjectInitializer(target_dir=tmp_path)
    initializer._create_manifest(force=True)

    result = yaml.safe_load(manifest_path.read_text())
    assert result["sessions"] == sessions, (
        "atdd init --force must preserve existing sessions; "
        f"got {result['sessions']!r}, expected {sessions!r}"
    )


def test_force_init_updates_version_while_preserving_sessions(tmp_path):
    """--force may update the manifest version key but must keep sessions intact."""
    sessions = [{"id": "1", "slug": "foo", "issue_number": 1, "status": "COMPLETE"}]
    manifest_path = _write_manifest(tmp_path / ".atdd", sessions)

    initializer = ProjectInitializer(target_dir=tmp_path)
    initializer._create_manifest(force=True)

    result = yaml.safe_load(manifest_path.read_text())
    assert result["sessions"] == sessions


def test_force_init_on_empty_sessions_stays_empty(tmp_path):
    """--force on a manifest with sessions: [] must not add spurious entries."""
    manifest_path = _write_manifest(tmp_path / ".atdd", [])

    initializer = ProjectInitializer(target_dir=tmp_path)
    initializer._create_manifest(force=True)

    result = yaml.safe_load(manifest_path.read_text())
    assert result["sessions"] == []


def test_fresh_init_creates_empty_sessions(tmp_path):
    """First-time init (no existing manifest) creates sessions: []."""
    (tmp_path / ".atdd").mkdir()
    manifest_path = tmp_path / ".atdd" / "manifest.yaml"
    assert not manifest_path.exists()

    initializer = ProjectInitializer(target_dir=tmp_path)
    initializer._create_manifest(force=False)

    result = yaml.safe_load(manifest_path.read_text())
    assert result["sessions"] == []
