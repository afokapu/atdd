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


# =============================================================================
# CASE B — the already-initialized repo (the case #1325 item 6 actually reported)
#
# sboupda's report was a MIGRATION inside a repo that had already run `atdd init`.
# Seeding at init only reaches brand-new repos: `atdd init` bails out with
# "already initialized" before it seeds, and `atdd init --force` is forbidden
# (#793). So the refresh verb — `atdd sync` — must re-seed, exactly as #1492 wired
# the hook refresh. Without that, this fix reaches nobody who already ran init.
# =============================================================================
def _already_initialized_repo(tmp_path: Path, *, gitignore: str) -> Path:
    """A repo that has already run `atdd init`, with a pre-fix .gitignore."""
    repo = _init_repo(tmp_path)
    atdd_dir = repo / ".atdd"
    atdd_dir.mkdir()
    # No toolkit.last_version and no github.repo → sync skips branch protection
    # (no network). One configured agent so sync does real work.
    (atdd_dir / "config.yaml").write_text("sync:\n  agents:\n    - claude\n")
    (repo / "CLAUDE.md").write_text("# consumer\n")
    (repo / ".gitignore").write_text(gitignore)
    return repo


def test_init_alone_does_not_reseed_an_already_initialized_repo(tmp_path: Path) -> None:
    """Documents the defect that makes the sync hook necessary.

    `atdd init` early-returns on an already-initialized repo, so it never reaches
    the seeding step — the entries stay missing. This is the guard-rail: if init
    ever starts re-seeding, this test tells us the sync path may be redundant.
    """
    repo = _already_initialized_repo(
        tmp_path, gitignore=".atdd/cache/\n.atdd/diagnostics/\n"
    )

    rc = ProjectInitializer(target_dir=repo).init()

    assert rc == 1, "init on an already-initialized repo is expected to bail out"
    content = (repo / ".gitignore").read_text()
    assert ".atdd/state/" not in content, (
        "init unexpectedly re-seeded; re-evaluate whether the sync path is still needed"
    )


def test_sync_reseeds_gitignore_on_already_initialized_repo(tmp_path: Path) -> None:
    """CASE B: the sanctioned refresh (`atdd sync`) backfills the missing entries.

    No --force. This is the path that reaches every repo initialised before the
    fix landed.
    """
    from atdd.coach.commands.sync import AgentConfigSync

    repo = _already_initialized_repo(
        tmp_path, gitignore=".atdd/cache/\n.atdd/diagnostics/\n"
    )

    rc = AgentConfigSync(target_dir=repo).sync()

    assert rc == 0, "sync must succeed on an already-initialized repo"
    content = (repo / ".gitignore").read_text()
    for entry in REQUIRED_ENTRIES:
        assert entry in content, (
            f"{entry!r} missing from .gitignore after `atdd sync`:\n{content}"
        )
    # Pre-existing entries must not be duplicated by the backfill.
    for entry in (".atdd/cache/", ".atdd/diagnostics/"):
        assert content.count(entry) == 1, f"{entry!r} duplicated by sync:\n{content}"


def test_sync_does_not_seed_gitignore_when_repo_never_initialized(tmp_path: Path) -> None:
    """sync is a refresher, never an installer (#1492's rule).

    A repo with no `.atdd/` never ran init; sync must not create `.atdd/` there and
    must not write atdd's ignore entries into a repo that does not use atdd.
    """
    from atdd.coach.commands.sync import AgentConfigSync

    repo = _init_repo(tmp_path)
    (repo / ".gitignore").write_text("node_modules/\n")

    AgentConfigSync(target_dir=repo).sync()

    assert not (repo / ".atdd").exists(), "sync must not create .atdd/ (not an installer)"
    content = (repo / ".gitignore").read_text()
    assert ".atdd/state/" not in content, (
        "sync seeded atdd entries into a repo that never ran init:\n" + content
    )
