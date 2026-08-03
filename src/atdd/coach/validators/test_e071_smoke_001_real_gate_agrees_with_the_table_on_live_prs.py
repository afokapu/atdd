# URN: test:govern-lifecycle:enforce-smoke-refactor-phase-substrate:E071-SMOKE-001-real-gate-agrees-with-the-table-on-live-prs
# Acceptance: acc:govern-lifecycle:E071-SMOKE-001-real-gate-agrees-with-the-table-on-live-prs
# WMBT: wmbt:govern-lifecycle:E071
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E071-SMOKE-001 — the real gate, over the repository's real open PRs.

An agent's own green proves little on a merge gate: get it wrong in one direction
and the 2026-05-13 incident ships again, get it wrong in the other and no PR in
the repo can merge. So this runs the real validator's real path — the real
``PRManager``, the real ``gh`` subprocesses, the live GitHub API, the real
evaluator — over whatever PRs are actually open, and asserts the invariant that
must hold whatever they happen to be:

    a Violation exists for a PR exactly when its linkage auto-closes AND its
    linked issue's phase is outside ``phase_labels.merge_allowed``.

Written as an invariant rather than against named PRs on purpose: PR #1673
(auto-closing #1622 at ``atdd:SMOKE``) is what made this issue reproducible
today, but it will merge, and a test anchored to it would then pass by having
nothing to check. The invariant keeps biting.

No collaborator is substituted — nothing is monkeypatched. The test skips when
the API is unreachable rather than asserting against a substitute.
"""
from __future__ import annotations

from typing import Dict, List

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.utils import pr_merge_eligibility as elig
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators import test_pr_merge_blocks_pre_smoke_close as mod

pytestmark = [pytest.mark.coach, pytest.mark.github_api]

REPO_ROOT = find_repo_root()


@pytest.fixture(scope="module")
def live_resolutions() -> List[Dict]:
    """Every open PR, resolved to its linked issue and atdd:<PHASE> through the API.

    This is the same real work ``scan_open_prs_for_pre_smoke_close`` does — the
    real ``PRManager``, one real ``gh`` subprocess per PR — kept in the test so the
    expected verdicts can be computed from the same live facts the gate sees.
    """
    try:
        mgr = PRManager(target_dir=REPO_ROOT)
        open_prs = mgr.fetch_open_prs()
    except Exception as exc:  # no gh, no auth, no network
        pytest.skip(f"live GitHub API unavailable: {exc}")

    resolutions: List[Dict] = []
    for pr in open_prs:
        number = pr.get("number")
        if not number:
            continue
        resolved = mgr.resolve_linked_issue(number)
        if resolved is None:
            continue
        resolved = dict(resolved)
        resolved["pr_number"] = number
        resolutions.append(resolved)

    if not resolutions:
        pytest.skip("no open PR resolves to an ATDD issue; nothing live to judge")
    return resolutions


def _auto_closing(resolution: Dict) -> bool:
    return resolution.get("strategy") in mod._AUTO_CLOSING_STRATEGIES


@pytest.mark.smoke
def test_the_real_gate_blocks_exactly_the_phases_outside_the_table(
    live_resolutions: List[Dict],
) -> None:
    blocked_locations = {
        v.location for v in mod.evaluate_pr_merge_violations(live_resolutions)
    }

    expected = {
        f"PR#{r['pr_number']}:0"
        for r in live_resolutions
        if _auto_closing(r) and elig.is_merge_blocked(r.get("phase_label"))
    }

    assert blocked_locations == expected, (
        "the real gate's verdict on the live open PRs disagrees with "
        "pr.convention.yaml::phase_labels.merge_allowed.\n"
        f"  merge-eligible phases: {list(elig.merge_allowed_phases())}\n"
        f"  gate blocked:  {sorted(blocked_locations)}\n"
        f"  table implies: {sorted(expected)}\n"
        f"  live resolutions: {live_resolutions!r}"
    )


@pytest.mark.smoke
def test_no_live_auto_close_at_smoke_passes_the_real_gate(
    live_resolutions: List[Dict],
) -> None:
    """The defect, measured against production rather than a fixture."""
    at_smoke = [
        r for r in live_resolutions if _auto_closing(r) and r.get("phase_label") == "SMOKE"
    ]
    if not at_smoke:
        pytest.skip("no open PR currently auto-closes an issue at atdd:SMOKE")

    blocked = {v.location for v in mod.evaluate_pr_merge_violations(live_resolutions)}
    for resolution in at_smoke:
        assert f"PR#{resolution['pr_number']}:0" in blocked, (
            f"PR #{resolution['pr_number']} would fire GitHub's auto-close on issue "
            f"#{resolution['issue_number']} at atdd:SMOKE, with REFACTOR never "
            "entered — the gate must block it"
        )


@pytest.mark.smoke
def test_a_live_auto_close_at_a_merge_eligible_phase_still_passes(
    live_resolutions: List[Dict],
) -> None:
    """A fix that blocks everything is not a fix — proved on real PRs, not fixtures."""
    allowed = set(elig.merge_allowed_phases())
    eligible = [
        r for r in live_resolutions if _auto_closing(r) and r.get("phase_label") in allowed
    ]
    if not eligible:
        pytest.skip(f"no open PR currently auto-closes an issue at {sorted(allowed)}")

    blocked = {v.location for v in mod.evaluate_pr_merge_violations(live_resolutions)}
    for resolution in eligible:
        assert f"PR#{resolution['pr_number']}:0" not in blocked, (
            f"PR #{resolution['pr_number']} auto-closes issue "
            f"#{resolution['issue_number']} at atdd:{resolution['phase_label']}, which "
            "the convention declares merge-eligible; blocking it would stop the repo"
        )
