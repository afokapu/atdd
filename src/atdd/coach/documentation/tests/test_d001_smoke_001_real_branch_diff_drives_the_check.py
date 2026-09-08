# URN: test:govern-documentation-obligation:check-declaration-integrity:D001-SMOKE-001-real-branch-diff-drives-the-integrity-check
# Acceptance: acc:govern-documentation-obligation:D001-SMOKE-001-real-branch-diff-drives-the-integrity-check
# WMBT: wmbt:govern-documentation-obligation:D001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""D001-SMOKE-001 — the check judged against a real branch diff.

Every other test for this feature hands the check a change set written by hand. That
proves the comparison, and proves nothing about the shape the comparison must meet: a
real change set comes out of `git diff --name-only origin/main..HEAD`, on a real
worktree, and is whatever that branch actually touched.

The distinction matters because the change set is the ONLY thing standing between a
declared obligation and a discharged one. A check that has only ever seen literals has
never met its input.

Real infrastructure: real git, real subprocess, real worktree, real commits. No fixture
tree and no double — the diff is this branch's own, so the test's premise decays if the
branch stops having commits, which is the correct failure.
"""
from __future__ import annotations

import subprocess

import pytest

from atdd.coach.documentation import check_declaration_integrity
from atdd.coach.utils.repo import find_repo_root

REPO_ROOT = find_repo_root()


def _real_change_set() -> list[str]:
    """The actual diff of this branch against the trunk it will merge into."""
    proc = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        pytest.skip(f"git could not produce a diff here: {proc.stderr.strip()[:120]}")
    return [line for line in proc.stdout.splitlines() if line.strip()]


@pytest.fixture(scope="module")
def change_set() -> list[str]:
    paths = _real_change_set()
    if not paths:
        pytest.skip("this branch has no commits past origin/main, so there is no diff to judge")
    return paths


def test_a_path_this_branch_really_touched_is_discharged(change_set: list[str]) -> None:
    touched = change_set[0]
    check = check_declaration_integrity(
        declaration={"impact": "change", "artifacts": [{"action": "modify", "path": touched}]},
        change_set=change_set,
    )

    assert check.complete is True
    assert check.discharged is True, f"{touched!r} is in this branch's real diff"
    assert check.findings == []


def test_a_path_this_branch_did_not_touch_is_not_discharged(change_set: list[str]) -> None:
    untouched = "docs/architecture/a-file-this-branch-never-wrote.adoc"
    assert untouched not in change_set, "fixture path must genuinely be absent from the real diff"

    check = check_declaration_integrity(
        declaration={"impact": "change", "artifacts": [{"action": "create", "path": untouched}]},
        change_set=change_set,
    )

    assert check.complete is True, "the declaration is well-formed; only its discharge failed"
    assert check.discharged is False
    assert any(untouched in f for f in check.findings), "the finding must name the undischarged path"


def test_the_real_diff_is_a_plain_list_of_path_strings(change_set: list[str]) -> None:
    """The wire shape core must hand the capability, taken from the real source.

    `atdd.extension.planner.docs` receives `change_set: list[str] | None` and treats
    None as COULD_NOT_CHECK. Confirming the real producer yields plain strings is what
    makes the seam's contract true in practice rather than on paper.
    """
    assert all(isinstance(p, str) and p for p in change_set)
