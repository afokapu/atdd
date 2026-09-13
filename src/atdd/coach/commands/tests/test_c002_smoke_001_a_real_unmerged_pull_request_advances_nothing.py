# URN: test:drive-state-machine:post-merge-advance-is-observable:C002-SMOKE-001-a-real-unmerged-pull-request-advances-nothing
# Acceptance: acc:drive-state-machine:C002-SMOKE-001-a-real-unmerged-pull-request-advances-nothing
# WMBT: wmbt:drive-state-machine:C002
# Phase: RED
# Layer: integration
"""C002-SMOKE-001 — against the live projection, an unmerged PR moves no phase.

The unit acceptances stub the PR read, so they prove the resolver consults the
merge — not that the field it consults is the one GitHub actually populates.
Whether a pull request merged is a fact only GitHub holds, so this one reads it
from the live projection.

THE CANDIDATE MUST BE AUTO-ADVANCEABLE, and the first draft of this test was not
and looked like a pass waiting to happen. It took the first open PR with a
closing reference — which linked an issue at PLANNED. PLANNED has no successor
in _NEXT_PHASE, so the resolver no-opped for a reason that has nothing to do with
the merge, and the assertion "no transition" held while the defect went
completely unexercised. Measured 2026-09-13: 9 of the 14 open PRs with a closing
reference link an issue at an auto-advanceable phase, and 5 do not. Selecting
from the wrong 5 is a green that proves nothing.

Measured the same day over all 853 pull requests: mergedAt is present if and only
if state == MERGED — 802 MERGED with it, 28 CLOSED without, 23 OPEN without, zero
counterexamples. That is why mergedAt is the AUTHORITY and state is the REASON,
and the second test asserts that relationship still holds.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from atdd.coach.commands import auto_phase as ap
from atdd.coach.commands.auto_phase import _NEXT_PHASE
from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo

pytestmark = [pytest.mark.github_api, pytest.mark.platform]


def _gh_json(root, *args):
    """Run gh and FAIL on a non-zero exit rather than reading empty output.

    README rule 4 / #1896: a command that errored must never read as "the
    repository has none". The exit code is asserted so the failure names it.
    """
    proc = subprocess.run(["gh", *args], cwd=str(root),
                          capture_output=True, text=True, timeout=90)
    assert proc.returncode == 0, (
        "gh " + " ".join(args) + f" exited {proc.returncode}: "
        f"{proc.stderr.strip()[:200]} — the query did not run, so its empty "
        "result is not an observation about this repository"
    )
    return json.loads(proc.stdout or "[]")


def _auto_advanceable_candidate(root, prs):
    """The first open PR whose linked issue sits at a phase that DOES advance.

    Returns (pr, result) or (None, None). target_dir is BOTH the Control-Root
    starting point AND the cwd the PR read runs in, so it must be the repository:
    an empty temp dir makes the read exit 1 with "not a git repository", the
    resolver report UNREADABLE, and the test fail without reaching the merge path.
    """
    for pr in prs:
        result = ap.resolve_pr_to_transition(pr["number"], target_dir=root)
        if result.action == "unreadable":
            continue
        if (result.current_phase or "").upper() in _NEXT_PHASE:
            return pr, result
    return None, None


def test_a_real_unmerged_pull_request_advances_nothing():
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self acceptance; this repository's PRs are the subject")
    root = find_repo_root()

    prs = _gh_json(root, "pr", "list", "--state", "open", "--limit", "50",
                   "--json", "number,state,mergedAt,closingIssuesReferences")
    linked = [p for p in prs if p.get("closingIssuesReferences")]
    if not linked:
        pytest.skip("no open pull request in this repository declares a closing reference")

    pr, result = _auto_advanceable_candidate(root, linked)
    if pr is None:
        pytest.skip(
            f"none of the {len(linked)} open linked pull requests reaches an "
            "auto-advanceable phase, so the merge premise cannot be exercised "
            "against the live projection right now"
        )

    assert pr["mergedAt"] is None, (
        f"PR #{pr['number']} is open and reports mergedAt={pr['mergedAt']!r}; "
        "the premise of this acceptance does not hold against the live projection"
    )
    assert result.action != "transition", (
        f"open PR #{pr['number']} (mergedAt=null) advances issue "
        f"#{result.issue_number} {result.current_phase} -> {result.next_phase}. "
        "Read from the live projection, not a fixture: the command moves the "
        "lifecycle from a pull request that has not merged."
    )
    assert "merge" in (result.reason or "").lower(), (
        f"the refusal does not name the merge: {result.reason!r}"
    )


def test_merged_at_and_state_agree_across_the_live_corpus():
    """The measured relationship the fix's design rests on.

    If these two ever disagree, mergedAt as the sole authority is wrong and the
    fix needs re-deciding — so the design premise is asserted, not assumed.
    """
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self acceptance; this repository's PRs are the subject")
    root = find_repo_root()

    prs = _gh_json(root, "pr", "list", "--state", "all", "--limit", "400",
                   "--json", "number,state,mergedAt")
    assert prs, "the pull-request query returned nothing; nothing was observed"

    disagreements = [
        p for p in prs
        if (p["mergedAt"] is not None) != (p["state"] == "MERGED")
    ]

    assert not disagreements, (
        "mergedAt and state disagree for "
        f"{[p['number'] for p in disagreements[:10]]} "
        f"({len(disagreements)} of {len(prs)}). The fix treats mergedAt as the "
        "authority and state as the reason; that rests on them never disagreeing."
    )
