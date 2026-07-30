# URN: test:govern-lifecycle:enforce-smoke-refactor-phase-substrate:E070-SMOKE-001-innocent-branch-not-blocked-by-a-sibling-offender
# Acceptance: acc:govern-lifecycle:E070-SMOKE-001-innocent-branch-not-blocked-by-a-sibling-offender
# WMBT: wmbt:govern-lifecycle:E070
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E070-SMOKE-001 — the real gate, on the push-event path, frees the innocent and
still blocks the offender.

This reproduces the live outage. ``atdd-validate.yml`` triggers on BOTH ``push`` and
``pull_request``. On the pull_request event ``GITHUB_REF=refs/pull/<N>/merge`` resolves
the PR without ever touching the branch leg — which is why E056's SMOKE test passed and
the bug shipped anyway. On the push event ``GITHUB_REF=refs/heads/<branch>`` falls into
the branch leg, which returned None, which meant "block repo-wide". Observed on CI runs
29235575570 (push, FAILED on PR #1461's violation) vs 29235577497 (same branch, same
commit, pull_request, PASSED).

Real infra, and no substituted collaborators: a real git repository with the branch
actually checked out (so ``PRManager._detect_branch`` runs a real ``git rev-parse``),
and a real stub ``gh`` executable on ``PATH`` (so ``_existing_pr_for_branch`` runs a
real subprocess and the URL parsing that was broken is exercised end to end). Only the
process boundary moves — ``monkeypatch.setenv``/``chdir`` are legitimate smoke setup
under ``tester.smoke.no-collaborator-substitution``; ``setattr`` on ``PRManager`` would
not be, and would hide the very bug this reproduces.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.validators import test_pr_merge_blocks_pre_smoke_close as mod

# The offending sibling: PR #1461 auto-closes #1193 while it is still at atdd:PLANNED.
_OFFENDER = [
    {"pr_number": 1461, "issue_number": 1193, "phase_label": "PLANNED", "strategy": "api"},
]


def _real_repo_on_branch(tmp_path: Path, branch: str) -> Path:
    """A real git repository with *branch* checked out."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *a: subprocess.run(a, cwd=repo, check=True, capture_output=True)
    run("git", "init", "-q")
    run("git", "config", "user.email", "smoke@atdd.test")
    run("git", "config", "user.name", "smoke")
    (repo / "README").write_text("smoke\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "base")
    run("git", "checkout", "-q", "-b", branch)
    return repo


def _stub_gh_on_path(tmp_path: Path, pr_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A real ``gh`` executable on PATH that prints *pr_url*, as the real one would.

    The production code shells out to ``gh pr list ... --jq .[0].url``; giving it a real
    binary keeps ``_existing_pr_for_branch`` and its URL-to-number parsing in the path
    under test instead of replacing them.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(f'#!/bin/sh\necho "{pr_url}"\n')
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def _push_event_on_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, branch: str, pr_url: str
) -> Path:
    """GitHub Actions' push-event environment: a heads ref, no PR number anywhere.

    Returns the repo root to hand to ``_current_pr_number`` — passed as an argument
    rather than patched onto the module, so no production attribute is replaced.
    """
    monkeypatch.delenv("ATDD_PR_NUMBER", raising=False)
    monkeypatch.delenv("PR_NUMBER", raising=False)
    monkeypatch.setenv("GITHUB_REF", f"refs/heads/{branch}")
    repo = _real_repo_on_branch(tmp_path, branch)
    _stub_gh_on_path(tmp_path, pr_url, monkeypatch)
    return repo


@pytest.mark.smoke
def test_innocent_branch_passes_on_a_push_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # An unrelated contributor's branch, whose own PR is #1384 and is clean.
    repo = _push_event_on_branch(
        monkeypatch,
        tmp_path,
        "feat/migrate-extension-package-id-grammar-to-include-persona",
        "https://github.com/afokapu/atdd/pull/1384",
    )

    all_violations = mod.evaluate_pr_merge_violations(_OFFENDER)
    assert [v.location for v in all_violations] == ["PR#1461:0"], "offender still seen"

    # The branch leg — the one that was dead — must name this run's own PR.
    current_pr = mod._current_pr_number(repo)
    assert current_pr == 1384

    blocking = mod.select_blocking_violations(all_violations, current_pr)
    assert blocking == [], "an innocent branch must not be failed by PR #1461's offense"

    # The real strict gate passes for the innocent branch.
    assert_disposition_satisfied(validator_id=mod._VALIDATOR_ID, violations=blocking)


@pytest.mark.smoke
def test_offending_branch_still_fails_on_a_push_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The offender's OWN branch, on the same push-event path: it must still be blocked.
    repo = _push_event_on_branch(
        monkeypatch,
        tmp_path,
        "feat/atdd-author-validate-against-canonical-schema",
        "https://github.com/afokapu/atdd/pull/1461",
    )

    all_violations = mod.evaluate_pr_merge_violations(_OFFENDER)
    blocking = mod.select_blocking_violations(all_violations, mod._current_pr_number(repo))
    assert [v.location for v in blocking] == ["PR#1461:0"]

    # Protective intent preserved: the offender's own run still fails the strict gate.
    with pytest.raises(BaseException):
        assert_disposition_satisfied(validator_id=mod._VALIDATOR_ID, violations=blocking)
