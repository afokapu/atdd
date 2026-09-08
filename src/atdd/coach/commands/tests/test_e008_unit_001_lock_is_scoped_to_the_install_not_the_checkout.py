# URN: test:integration-hardening:run-upgrade-unattended:E008-UNIT-001-lock-is-scoped-to-the-install-not-the-checkout
# Acceptance: acc:integration-hardening:E008-UNIT-001-lock-is-scoped-to-the-install-not-the-checkout
# WMBT: wmbt:integration-hardening:E008
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E008-UNIT-001 — the lock is scoped to the install, never to a checkout.

RED Test for acc:integration-hardening:E008-UNIT-001-lock-is-scoped-to-the-install-not-the-checkout
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:E008
Purpose: The load-bearing property of the whole WMBT. A lock under a worktree's
own .atdd/ would give sixty agents sixty locks and serialise nothing, while
looking protected — the worst of both.
"""
from __future__ import annotations

import pytest

from ._upgrade_unattended_helpers import require_symbol, write_config

pytestmark = [pytest.mark.platform]


@pytest.mark.platform
def test_e008_unit_001_two_checkouts_resolve_to_one_lock(tmp_path, monkeypatch):
    lock_path = require_symbol("upgrade_lock_path")

    repo_a = tmp_path / "feat-worktree-a"
    repo_b = tmp_path / "feat-worktree-b"
    for repo in (repo_a, repo_b):
        repo.mkdir(parents=True)
        write_config(repo, last_version="3.106.0")

    monkeypatch.chdir(repo_a)
    from_a = lock_path()
    monkeypatch.chdir(repo_b)
    from_b = lock_path()

    assert from_a == from_b, (
        "two checkouts sharing one install must contend for the same lock; "
        f"got {from_a} and {from_b}"
    )


@pytest.mark.platform
def test_e008_unit_001_lock_lives_outside_every_checkout(tmp_path, monkeypatch):
    lock_path = require_symbol("upgrade_lock_path")

    repo = tmp_path / "feat-worktree-a"
    repo.mkdir(parents=True)
    write_config(repo, last_version="3.106.0")
    monkeypatch.chdir(repo)

    resolved = lock_path().resolve()

    assert not resolved.is_relative_to(repo.resolve()), (
        f"the lock must not live inside a checkout; {resolved} is under {repo}"
    )
    assert ".atdd" not in resolved.parts or not resolved.is_relative_to(repo.resolve()), (
        f"the lock must not live under a per-worktree .atdd/ control root; got {resolved}"
    )
