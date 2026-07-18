# Phase: RED
# Layer: integration
# Assertion: behavioral
"""#1325 item 6 — `atdd init` must gitignore the operational artifacts it writes.

Before this fix the initializer seeded only ``.atdd/cache/`` and
``.atdd/diagnostics/``. But the State Store is now the sole operational registry
(``.atdd/state/state.sqlite*``, written on every run), and a legacy-manifest
migration writes ``.atdd/manifest.migrated.yaml`` (``manifest_import._BACKUP_NAME``).
Neither was gitignored, so a consumer that upgraded was left with a binary SQLite
store + a migration backup as untracked noise — easy to commit by accident.

The intended entries already live in the toolkit's own ``.gitignore``; this pins
that `atdd init` writes the same set. Idempotent: a second seed adds no dupes.

HERMETIC: a throwaway `git init` under tmp_path; no network, no real repo touched.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.initializer import ProjectInitializer

pytestmark = [pytest.mark.coach]

# The per-checkout operational artifacts `atdd init` must keep out of git history.
REQUIRED_ENTRIES = (
    ".atdd/cache/",
    ".atdd/diagnostics/",
    ".atdd/state/",
    ".atdd/manifest.migrated.yaml",
)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)],
        check=True,
        capture_output=True,
    )
    return repo


def test_seed_gitignore_entries_covers_state_and_migrated_manifest(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    initializer = ProjectInitializer(target_dir=repo)
    assert hasattr(initializer, "_seed_gitignore_entries"), (
        "RED: ProjectInitializer._seed_gitignore_entries() not implemented yet"
    )

    initializer._seed_gitignore_entries()

    gitignore = repo / ".gitignore"
    assert gitignore.is_file(), "init did not write a .gitignore"
    content = gitignore.read_text()
    for entry in REQUIRED_ENTRIES:
        assert entry in content, (
            f"{entry!r} missing from .gitignore after init:\n{content}"
        )


def test_seed_gitignore_entries_is_idempotent(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    initializer = ProjectInitializer(target_dir=repo)

    initializer._seed_gitignore_entries()
    initializer._seed_gitignore_entries()

    content = (repo / ".gitignore").read_text()
    for entry in REQUIRED_ENTRIES:
        assert content.count(entry) == 1, (
            f"{entry!r} duplicated on re-seed:\n{content}"
        )
