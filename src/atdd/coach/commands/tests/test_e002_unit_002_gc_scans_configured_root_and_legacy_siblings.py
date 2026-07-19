# URN: test:place-worktrees:place-worktrees:E002-UNIT-002-gc-scans-configured-root-and-legacy-siblings
# Acceptance: acc:place-worktrees:E002-UNIT-002-gc-scans-configured-root-and-legacy-siblings
# WMBT: wmbt:place-worktrees:E002
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""E002-UNIT-002 — gc scans both roots, and never treats the root as an orphan.

Issue #1524. The Phase 0 audit found two defects in `worktree_gc.gc`, and they
pull in opposite directions:

1. SILENT UNDER-SCAN. The candidate filter is `if "-" not in candidate.name`,
   so a configured root named `worktrees` is skipped outright — gc returns zero
   orphans after migration rather than misbehaving visibly. Worktrees inside it
   are never even considered.

2. DESTRUCTIVE OVER-REACH. The same naming filter is the ONLY thing keeping the
   root itself out of the candidate set. Configure `worktree_root: atdd-worktrees`
   — a name with a hyphen — and the root becomes a candidate; `_is_orphan`
   rglobs the whole subtree and, if it happens to contain exactly one
   `.launch_prompt.txt`, `gc(apply=True)` would `rmtree` every worktree under it.

So the root must be excluded EXPLICITLY, by identity, not by the shape of its
name. Both halves are asserted here because a fix for either one alone leaves
the other live.

Phase RED: fails because gc scans only `repo_root.parent` and filters by name.
Phase GREEN: gc scans both locations and excludes the configured root by path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from atdd.coach.commands.worktree_gc import gc

pytestmark = [pytest.mark.coach]


def _orphan(path: Path) -> Path:
    """An orphan by gc's own definition: only a .launch_prompt.txt inside."""
    path.mkdir(parents=True, exist_ok=True)
    (path / ".launch_prompt.txt").write_text("stale launch prompt\n")
    return path


def _repo(tmp_path: Path, worktree_root: str) -> Path:
    root = tmp_path / "main"
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\n"
        "github:\n"
        "  repo: owner/repo\n"
        "  default_branch: main\n"
        f"worktree_root: {worktree_root}\n"
    )
    return root


def test_e002_unit_002_gc_scans_configured_root_and_legacy_siblings(tmp_path):
    root = _repo(tmp_path, "worktrees")

    # One orphan in each location, while old worktrees drain.
    legacy_orphan = _orphan(root.parent / "feat-legacy-orphan")
    configured_orphan = _orphan(root / "worktrees" / "feat-configured-orphan")

    with patch("atdd.coach.commands.worktree_gc._real_worktree_paths", return_value=set()):
        found = {p.resolve() for p in gc(root)}

    assert legacy_orphan.resolve() in found, (
        "gc missed the orphan at the legacy sibling location"
    )
    assert configured_orphan.resolve() in found, (
        "gc missed the orphan under the configured worktree_root — the "
        '`"-" not in candidate.name` filter skips a directory named '
        '"worktrees" outright, so gc silently reports nothing post-migration'
    )


def test_e002_unit_002_hyphenated_root_is_scanned_into_but_never_eaten(tmp_path):
    """Scan INTO the configured root; never classify the root ITSELF as orphan.

    The destructive half of this hazard is CREATED by the fix for the silent
    half. Today `gc` scans only `repo_root.parent`, so a root at
    `main/atdd-worktrees` is unreachable and cannot be eaten — the second
    assertion below would pass vacuously on its own. It is paired with the
    first, which is red today, so the test cannot go green until gc scans the
    root AND the exclusion is real. `_is_orphan` counts non-directory files
    only, so a root containing one worktree holding one `.launch_prompt.txt`
    matches its heuristic exactly.
    """
    root = _repo(tmp_path, "atdd-worktrees")
    worktree_root = root / "atdd-worktrees"

    # One orphan inside a HYPHENATED root — the name shape that makes the root
    # itself a candidate once gc learns to look there.
    inner_orphan = _orphan(worktree_root / "feat-real-work")

    with patch("atdd.coach.commands.worktree_gc._real_worktree_paths", return_value=set()):
        found = {p.resolve() for p in gc(root)}

    assert inner_orphan.resolve() in found, (
        "gc did not scan into the configured worktree_root at all"
    )
    assert worktree_root.resolve() not in found, (
        f"gc classified the configured worktree_root {worktree_root} as an "
        "orphan; with apply=True that rmtree's every worktree under it. The "
        "root must be excluded explicitly, not by its name containing no hyphen"
    )
