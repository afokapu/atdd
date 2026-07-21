# URN: test:place-worktrees:place-worktrees:E001-UNIT-002-absent-config-is-bit-identical-to-today
# Acceptance: acc:place-worktrees:E001-UNIT-002-absent-config-is-bit-identical-to-today
# WMBT: wmbt:place-worktrees:E001
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""E001-UNIT-002 — with no `worktree_root` configured, placement is unchanged.

Issue #1524, Decision 2: the migration is forward-only. An upgraded consumer that
configures nothing must see placement bit-identical to the flat-sibling layout it
had before, and the resolver must report the default root rather than raising on
the missing key.

This is the other half of E001-UNIT-001: that one pins that configuration is
HONOURED, this one pins that its ABSENCE changes nothing. A resolver that
satisfies only the first could still break every existing repo.

Phase RED: fails on the import — `atdd.coach.commands.worktree_placement` does
not exist. The default-placement half of this test passes today by construction
(that IS today's behaviour), so the resolver's own contract is what is pinned.
Phase GREEN: the resolver returns `..` for an absent key and derives the
identical flat-sibling path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

SLUG = "config-driven-worktree-placement"
PREFIX = "feat"


def _repo(tmp_path: Path, *, worktree_root: str | None) -> Path:
    """A control root, optionally carrying a `worktree_root` key."""
    root = tmp_path / "main"
    (root / ".atdd").mkdir(parents=True)
    config = "version: '1.0'\ngithub:\n  repo: owner/repo\n  default_branch: main\n"
    if worktree_root is not None:
        config += f"worktree_root: {worktree_root}\n"
    (root / ".atdd" / "config.yaml").write_text(config)
    return root


def test_e001_unit_002_absent_config_is_bit_identical_to_today(tmp_path):
    from atdd.coach.commands.worktree_placement import (
        resolve_worktree_path,
        resolve_worktree_root,
    )

    root = _repo(tmp_path, worktree_root=None)

    # The missing key must resolve to the documented default, not raise.
    assert resolve_worktree_root(root) == Path(".."), (
        "an absent worktree_root must default to '..' (today's flat sibling)"
    )

    # And the derived path must be exactly what the pre-change code produced:
    #     branch.py:418  worktree_path = self.target_dir.parent / f"{prefix}-{slug}"
    legacy = root.parent / f"{PREFIX}-{SLUG}"
    assert resolve_worktree_path(root, PREFIX, SLUG) == legacy, (
        "with no worktree_root configured, placement must be bit-identical to "
        "the flat-sibling layout"
    )

    # A configured root must move it — otherwise the default is not a default,
    # it is a hardcode wearing a config key's name.
    configured_root = _repo(tmp_path / "other", worktree_root="worktrees")
    assert resolve_worktree_path(configured_root, PREFIX, SLUG) == (
        configured_root / "worktrees" / f"{PREFIX}-{SLUG}"
    )
