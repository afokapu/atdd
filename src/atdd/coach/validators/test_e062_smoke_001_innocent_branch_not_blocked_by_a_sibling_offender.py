# URN: test:govern-lifecycle:enforce-smoke-refactor-phase-substrate:E062-SMOKE-001-innocent-branch-not-blocked-by-a-sibling-offender
# Acceptance: acc:govern-lifecycle:E062-SMOKE-001-innocent-branch-not-blocked-by-a-sibling-offender
# WMBT: wmbt:govern-lifecycle:E062
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E062-SMOKE-001 — the real gate, on the push-event path, frees the innocent and
still blocks the offender.

This reproduces the live outage. ``atdd-validate.yml`` triggers on BOTH ``push`` and
``pull_request``. On the pull_request event ``GITHUB_REF=refs/pull/<N>/merge`` resolves
the PR without ever touching the branch leg — which is why E056's SMOKE test passed and
the bug shipped anyway. On the push event ``GITHUB_REF=refs/heads/<branch>`` falls into
the branch leg, which returned None, which meant "block repo-wide". Observed on CI runs
29235575570 (push, FAILED on PR #1461's violation) vs 29235577497 (same branch, same
commit, pull_request, PASSED).

Real infra: the real validator module, the real PRManager branch-resolution seam, the
real evaluator, and the real assert_disposition_satisfied gate. Only the ``gh``
subprocess boundary is stubbed, so the URL parsing that was broken is exercised for
real.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.validators import test_pr_merge_blocks_pre_smoke_close as mod

# The offending sibling: PR #1461 auto-closes #1193 while it is still at atdd:PLANNED.
_OFFENDER = [
    {"pr_number": 1461, "issue_number": 1193, "phase_label": "PLANNED", "strategy": "api"},
]


def _push_event_on_branch(
    monkeypatch: pytest.MonkeyPatch, branch: str, pr_url: str
) -> None:
    """GitHub Actions' push-event environment: a heads ref, no PR number anywhere."""
    monkeypatch.delenv("ATDD_PR_NUMBER", raising=False)
    monkeypatch.delenv("PR_NUMBER", raising=False)
    monkeypatch.setenv("GITHUB_REF", f"refs/heads/{branch}")
    monkeypatch.setattr(PRManager, "_detect_branch", lambda self: branch, raising=True)
    monkeypatch.setattr(
        PRManager, "_existing_pr_for_branch", lambda self, b: pr_url, raising=True
    )


@pytest.mark.smoke
def test_innocent_branch_passes_on_a_push_event(monkeypatch: pytest.MonkeyPatch) -> None:
    # An unrelated contributor's branch, whose own PR is #1384 and is clean.
    _push_event_on_branch(
        monkeypatch,
        "feat/migrate-extension-package-id-grammar-to-include-persona",
        "https://github.com/afokapu/atdd/pull/1384",
    )

    all_violations = mod.evaluate_pr_merge_violations(_OFFENDER)
    assert [v.location for v in all_violations] == ["PR#1461:0"], "offender still seen"

    # The branch leg — the one that was dead — must name this run's own PR.
    current_pr = mod._current_pr_number()
    assert current_pr == 1384

    blocking = mod.select_blocking_violations(all_violations, current_pr)
    assert blocking == [], "an innocent branch must not be failed by PR #1461's offense"

    # The real strict gate passes for the innocent branch.
    assert_disposition_satisfied(validator_id=mod._VALIDATOR_ID, violations=blocking)


@pytest.mark.smoke
def test_offending_branch_still_fails_on_a_push_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The offender's OWN branch, on the same push-event path: it must still be blocked.
    _push_event_on_branch(
        monkeypatch,
        "feat/atdd-author-validate-against-canonical-schema",
        "https://github.com/afokapu/atdd/pull/1461",
    )

    all_violations = mod.evaluate_pr_merge_violations(_OFFENDER)
    blocking = mod.select_blocking_violations(all_violations, mod._current_pr_number())
    assert [v.location for v in blocking] == ["PR#1461:0"]

    # Protective intent preserved: the offender's own run still fails the strict gate.
    with pytest.raises(BaseException):
        assert_disposition_satisfied(validator_id=mod._VALIDATOR_ID, violations=blocking)
