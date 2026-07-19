# URN: test:train:coach:place-worktrees:E2E-001-place-worktrees-journey
# Train: train:coach:place-worktrees
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: End-to-end journey for the place-worktrees train — over a real git
#          repository and a real State Store, one configured `worktree_root`
#          decides placement for every consumer: the resolver, the launch prompt
#          handed to a spawned agent, the orphan scanner, and relocation. No
#          mocks: real `git worktree add`/`move`, real sqlite store, real config.
"""Train-level E2E: one config key, and everything downstream agrees.

Exercises the placement train as a working whole:

1. resolve  — `worktree_root` decides where a branch's worktree belongs, and the
   flat-sibling default is what an unconfigured repo still gets
2. create   — a real `git worktree add` at the resolved path, which git then
   reports at that path and nowhere else
3. announce — the launch prompt names the directory that was actually created,
   rather than the `../{branch}` string it used to manufacture
4. scan     — `worktree gc` finds orphans under BOTH the configured root and the
   legacy location, and never classifies the configured root as an orphan itself
5. relocate — a bound worktree moves under the configured root with git and the
   store committing together, and an unbound worktree is declined rather than
   guessed at

Step 5's decline is what makes the store↔git drift (#1529) a sibling of #1524
rather than a prerequisite: 77 of 113 worktrees on this repo carry no binding,
and the offer simply does not fire for them.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.session_template import build_context
from atdd.coach.commands.worktree_gc import gc
from atdd.coach.commands.worktree_placement import (
    relocate_worktree,
    relocation_offer,
    resolve_worktree_path,
    resolve_worktree_root,
)
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.coach]

ISSUE = 1524
SLUG = "config-driven-worktree-placement"
PREFIX = "feat"
BRANCH = f"{PREFIX}/{SLUG}"
WORKTREE_ROOT = "worktrees"


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout


def _registered(root: Path) -> set:
    return {
        Path(line.split(" ", 1)[1]).resolve()
        for line in _git("worktree", "list", "--porcelain", cwd=root).splitlines()
        if line.startswith("worktree ")
    }


def _repo(tmp_path: Path, *, worktree_root: str | None) -> Path:
    root = tmp_path / "main"
    root.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=root)
    _git("config", "user.email", "test@example.com", cwd=root)
    _git("config", "user.name", "Test", cwd=root)
    (root / "README.md").write_text("seed\n")
    _git("add", "README.md", cwd=root)
    _git("commit", "-q", "-m", "seed", cwd=root)
    (root / ".atdd").mkdir()
    config = "version: '1.0'\ngithub:\n  repo: owner/repo\n  default_branch: main\n"
    if worktree_root is not None:
        config += f"worktree_root: {worktree_root}\n"
    (root / ".atdd" / "config.yaml").write_text(config)
    return root


def _bind(root: Path, slug: str, worktree: Path, issue: int) -> None:
    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        store.objects.upsert(
            slug,
            WORK_ITEM_KIND,
            state="RED",
            data={
                "issue_number": issue,
                "type": "implementation",
                "branch": f"{PREFIX}/{slug}",
                "worktree_path": str(worktree),
            },
        )
        store.external_refs.link(slug, GITHUB_PROVIDER, "issue", str(issue))
        conn.commit()
    finally:
        conn.close()


def _binding(root: Path, slug: str) -> str | None:
    conn = connect(init_state_store(start=root))
    try:
        obj = StateStore(conn).objects.get(slug)
        return (obj.data or {}).get("worktree_path") if obj else None
    finally:
        conn.close()


def test_place_worktrees_journey_smoke(tmp_path, monkeypatch):
    # -- 1. resolve ------------------------------------------------------
    root = _repo(tmp_path / "configured", worktree_root=WORKTREE_ROOT)
    assert resolve_worktree_root(root) == Path(WORKTREE_ROOT)

    resolved = resolve_worktree_path(root, PREFIX, SLUG)
    assert resolved == (root / WORKTREE_ROOT / f"{PREFIX}-{SLUG}").resolve()

    # The unconfigured repo still gets the flat sibling — forward-only.
    plain = _repo(tmp_path / "plain", worktree_root=None)
    assert resolve_worktree_root(plain) == Path("..")
    assert resolve_worktree_path(plain, PREFIX, SLUG) == (
        plain.parent / f"{PREFIX}-{SLUG}"
    ).resolve()

    # -- 2. create -------------------------------------------------------
    resolved.parent.mkdir(parents=True, exist_ok=True)
    _git("worktree", "add", "-q", "-b", BRANCH, str(resolved), cwd=root)
    assert resolved in _registered(root)
    assert not (root.parent / f"{PREFIX}-{SLUG}").exists(), (
        "a directory appeared at the legacy location despite worktree_root"
    )

    # -- 3. announce -----------------------------------------------------
    # ATDD_REPO_ROOT is the toolkit's own first-priority root marker, so this
    # points the REAL `find_repo_root` at the real temp repo rather than
    # substituting it. A SMOKE test that stubbed the collaborator here would
    # prove nothing about what a spawned agent is actually told.
    monkeypatch.setenv("ATDD_REPO_ROOT", str(root))
    body = (
        "# T\n\n## Issue Metadata\n\n| Field | Value |\n|-------|-------|\n"
        f"| Branch | `{BRANCH}` |\n"
    )
    announced = build_context(ISSUE, body, title="T").worktree_path
    assert not str(announced).startswith("../"), (
        "the launch prompt still manufactures a relative ../ path"
    )
    assert Path(announced) == resolved, (
        f"the launch prompt sends a spawned agent to {announced}, but the "
        f"worktree was created at {resolved}"
    )

    # -- 4. scan ---------------------------------------------------------
    legacy_orphan = root.parent / "feat-legacy-orphan"
    legacy_orphan.mkdir(parents=True)
    (legacy_orphan / ".launch_prompt.txt").write_text("stale\n")

    configured_orphan = root / WORKTREE_ROOT / "feat-configured-orphan"
    configured_orphan.mkdir(parents=True)
    (configured_orphan / ".launch_prompt.txt").write_text("stale\n")

    orphans = {p.resolve() for p in gc(root)}
    assert legacy_orphan.resolve() in orphans
    assert configured_orphan.resolve() in orphans, (
        "gc did not scan the configured root while legacy worktrees drain"
    )
    assert resolved not in orphans, "gc classified a live worktree as an orphan"
    assert (root / WORKTREE_ROOT).resolve() not in orphans, (
        "gc classified the configured root itself as an orphan — apply=True "
        "would remove every worktree beneath it"
    )

    # -- 5. relocate -----------------------------------------------------
    other = "relocate-me"
    legacy_worktree = root.parent / f"{PREFIX}-{other}"
    _git("worktree", "add", "-q", "-b", f"{PREFIX}/{other}", str(legacy_worktree), cwd=root)
    (legacy_worktree / "uncommitted.txt").write_text("survives\n")
    _bind(root, other, legacy_worktree, 9999)

    offer = relocation_offer(root, legacy_worktree)
    assert offer.offered is True
    assert offer.destination == resolve_worktree_path(root, PREFIX, other)

    relocate_worktree(root, other, offer.destination)
    assert offer.destination.is_dir()
    assert not legacy_worktree.exists()
    assert (offer.destination / "uncommitted.txt").read_text() == "survives\n"
    assert offer.destination.resolve() in _registered(root)
    assert _binding(root, other) == str(offer.destination), (
        "relocation left the store naming the old path — the stale-binding "
        "class this train exists to avoid manufacturing"
    )

    # An unbound worktree is declined, not guessed at.
    unbound = root.parent / "cw-phase0"
    unbound.mkdir(parents=True)
    (unbound / "scratch.txt").write_text("ad-hoc\n")
    declined = relocation_offer(root, unbound)
    assert declined.offered is False
    assert declined.reason == "unbound"
    assert unbound.exists() and (unbound / "scratch.txt").exists()
