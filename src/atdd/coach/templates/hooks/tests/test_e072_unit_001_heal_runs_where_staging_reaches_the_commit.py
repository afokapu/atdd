# URN: test:govern-lifecycle:close-substrate-friction-regressions:E072-UNIT-001-heal-runs-where-staging-reaches-the-commit
# Acceptance: acc:govern-lifecycle:E072-UNIT-001-heal-runs-where-staging-reaches-the-commit
# WMBT: wmbt:govern-lifecycle:E072
# Phase: GREEN
# Layer: backend.unit
"""E072-UNIT-001 — the mirror resync runs from pre-commit, and a resync that fails
is reported as a failure rather than swallowed into a success notice (#1888).

The block under test is extracted from the shipped pre-commit template, so this
cannot pass against a hook body the repo no longer ships.
"""
from __future__ import annotations

import pytest

from ._e072_registry_harness import (
    MIRRORS, extract_block, make_repo, run_block, HOOKS_DIR,
)

pytestmark = [pytest.mark.coach]

HEADING = "# --- Registry mirror auto-heal"


@pytest.fixture()
def heal_block() -> str:
    return extract_block("pre-commit", HEADING)


def test_drift_is_resynced_and_staged(tmp_path, heal_block) -> None:
    repo, env = make_repo(tmp_path)
    (repo / ".drift").touch()

    result = run_block(heal_block, repo, env)

    assert result.returncode == 0, result.stderr
    assert "resynced" in result.stderr
    staged = run_block("git diff --cached --name-only", repo, env).stdout.split()
    assert "plan/_wagons.yaml" in staged, (
        "the resynced mirror was not staged, so it cannot join the commit"
    )
    # An unchanged mirror produces no cached diff, so presence-in-staged is the
    # wrong property to assert across all three. The property that matters is
    # that the heal leaves NOTHING behind in the worktree: a mirror resynced but
    # not staged is exactly the #1888 failure, one stage earlier.
    unstaged = run_block("git diff --name-only", repo, env).stdout.split()
    left_behind = [m for m in MIRRORS if m in unstaged]
    assert not left_behind, f"resynced but not staged, so it would be abandoned: {left_behind}"


def test_no_drift_is_silent_and_stages_nothing(tmp_path, heal_block) -> None:
    repo, env = make_repo(tmp_path)

    result = run_block(heal_block, repo, env)

    assert result.returncode == 0
    assert result.stderr.strip() == "", f"unexpected chatter: {result.stderr!r}"
    assert run_block("git diff --cached --name-only", repo, env).stdout.strip() == ""


def test_a_failed_resync_is_never_reported_as_a_heal(tmp_path, heal_block) -> None:
    """THE POINT. The shipped pre-push ran `... --yes || true` and printed its
    success notice either way, so a resync that exploded looked identical to one
    that worked."""
    repo, env = make_repo(tmp_path)
    (repo / ".drift").touch()
    (repo / ".healfails").touch()

    result = run_block(heal_block, repo, env)

    assert "FAILED" in result.stderr
    assert "NOT resynced" in result.stderr
    assert "resynced and included in this commit" not in result.stderr


def test_a_failed_resync_does_not_strand_the_operators_work(tmp_path, heal_block) -> None:
    """Refusing at commit time would strand work; pre-push refuses instead, where
    a refusal costs nothing because the commits already exist."""
    repo, env = make_repo(tmp_path)
    (repo / ".drift").touch()
    (repo / ".healfails").touch()

    assert run_block(heal_block, repo, env).returncode == 0


def test_pre_push_does_not_carry_the_heal(tmp_path) -> None:
    """Staging in pre-push cannot reach the push, so the heal must not live there."""
    text = (HOOKS_DIR / "pre-push").read_text(encoding="utf-8")
    assert HEADING not in text, (
        "The auto-heal block appears in pre-push. git resolves the refs it will\n"
        "send before this hook runs, so the resync would be staged and abandoned."
    )
