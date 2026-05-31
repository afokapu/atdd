# URN: component:govern-lifecycle:enforcement-substrate:test_pr_closes_keyword_discipline:backend:domain
# Runtime: python
# Purpose: Enforces coach.pr.closes-keyword-discipline — the PR body is the single
#          source of truth for auto-close intent; commit-injected and negated
#          closing keywords that GitHub's parser mishandles are violations (#928 Gap 3).
"""
Validator for ``coach.pr.closes-keyword-discipline`` (issue #928 Gap 3).

GitHub's closing-keyword parser is silently buggy in two ways ATDD hits
repeatedly with its multi-section umbrella PRs:

  1. NEGATED body keyword — a PR body phrase like ``Does NOT close #N``
     still fires auto-close, because the parser ignores negation.
  2. COMMIT-INJECTED close — a commit message body such as
     ``Closes #919 Sections B and C`` makes GitHub auto-close #919 on
     merge even when the PR body deliberately uses ``Refs #919`` (the
     2026-05-31 #927 incident). The keyword lives in immutable commit
     history, outside the editable PR-body control point.

This validator makes the **PR body the single source of truth** for
auto-close intent: the set of issues GitHub will actually auto-close
(``closingIssuesReferences`` from the GraphQL API) must equal the set of
issues the body affirmatively closes, and the body must carry no negated
closing keyword.

Convention: ``src/atdd/coach/conventions/pr.convention.yaml``
            (rule ``coach.pr.closes-keyword-discipline``).

Emits structured ``Violation`` records the disposition gate fails on under
``strict`` disposition. Run: ``atdd validate coach``.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.coach, pytest.mark.github_api]


_RULE = bind_rule("coach.pr.closes-keyword-discipline")
_VALIDATOR_ID = "pr_closes_keyword_discipline"

REPO_ROOT = find_repo_root()

# Affirmative closing-keyword + issue-number regex. Mirrors
# PRManager._CLOSING_RE and GitHub's documented auto-close keyword set.
_CLOSING_RE = re.compile(
    r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)",
    re.IGNORECASE,
)

# Negation tokens that, immediately before a closing keyword on the same
# line, signal the author did NOT intend the close — but GitHub fires
# auto-close anyway (the "Does NOT close #N" bite). Scanned only within the
# same-line text preceding the keyword.
_NEGATION_RE = re.compile(
    r"\b(?:not|no|never|cannot|can'?t|won'?t|don'?t|doesn'?t|didn'?t|without)\b",
    re.IGNORECASE,
)

# How far back (chars, same line) to look for a negation before a keyword.
_NEGATION_WINDOW = 40


def _body_close_refs(body: str) -> Tuple[Set[int], Set[int]]:
    """Split a PR body's closing-keyword references into (affirmative, negated).

    For each ``Closes/Fixes/Resolves #N`` match, look at the same-line text
    immediately preceding it; if a negation token appears there the close is
    classified as *negated* (GitHub closes it anyway — a violation), else
    *affirmative* (the legitimate, intended way to declare an auto-close).
    """
    affirmative: Set[int] = set()
    negated: Set[int] = set()
    if not body:
        return affirmative, negated
    for m in _CLOSING_RE.finditer(body):
        num = int(m.group(1))
        window_start = max(0, m.start() - _NEGATION_WINDOW)
        preceding = body[window_start:m.start()]
        # Restrict to the same line so a negation two lines up does not bleed.
        preceding = preceding.rsplit("\n", 1)[-1]
        if _NEGATION_RE.search(preceding):
            negated.add(num)
        else:
            affirmative.add(num)
    return affirmative, negated


def _commit_close_refs(commits: Sequence[dict]) -> List[Tuple[str, int]]:
    """Return ``(sha, issue_number)`` for every closing keyword in any commit."""
    refs: List[Tuple[str, int]] = []
    for commit in commits or []:
        message = commit.get("message") or ""
        sha = commit.get("sha") or ""
        for m in _CLOSING_RE.finditer(message):
            refs.append((sha, int(m.group(1))))
    return refs


def evaluate_closes_keyword_violations(
    pr_records: Sequence[dict],
) -> List[Violation]:
    """Pure evaluator — no GitHub access — so unit tests drive it from fixtures.

    Args:
        pr_records: Sequence of dicts shaped:
            ``{"pr_number": int, "body": str,
               "commits": [{"sha": str, "message": str}, ...],
               "closing_refs": [int, ...]}``
            where ``closing_refs`` is the normalized ``closingIssuesReferences``
            (what GitHub will actually auto-close on merge).

    Emits one Violation per issue that GitHub will auto-close
    (``closing_refs``) without an affirmative ``Closes #N`` in the PR body.
    Each violation enumerates every detected cause (a negated body keyword,
    closing keyword(s) in commit messages) so the fix is complete — the
    #927 incident had BOTH at once, and fixing only one leaves the
    auto-close firing.

    The gate is anchored to ``closing_refs`` (what GitHub actually closes)
    on purpose: a harmless "this does not close #N" body mention that GitHub
    correctly ignored is NOT flagged, avoiding false positives.
    """
    violations: List[Violation] = []
    log = logging.getLogger(__name__)

    for rec in pr_records:
        if not rec:
            continue
        pr_number = rec.get("pr_number")
        if not pr_number:
            continue
        body = rec.get("body") or ""
        commits = rec.get("commits") or []
        closing_refs = {int(n) for n in (rec.get("closing_refs") or []) if n}

        affirmative, negated = _body_close_refs(body)
        commit_closes = _commit_close_refs(commits)

        # An issue that GitHub will auto-close on merge but whose close the
        # PR body does NOT affirmatively declare. The body is the single
        # source of truth for auto-close intent; a divergence means the close
        # is being injected by a negated body phrase (parser ignores the
        # negation) and/or a commit message (immutable, outside the editable
        # body). Enumerate ALL causes — each needs its own fix.
        for num in sorted(closing_refs - affirmative):
            shas = sorted({sha for sha, n in commit_closes if n == num and sha})
            causes: List[str] = []
            if num in negated:
                causes.append(
                    "a negated/qualified closing keyword in the PR body "
                    "(GitHub ignores the negation and closes anyway) — "
                    f"rewrite that phrase to `Refs #{num}`"
                )
            if shas:
                where = ", ".join(s[:8] for s in shas)
                causes.append(
                    f"a closing keyword in commit message(s) {where} "
                    f"(immutable history, outside the editable body) — "
                    f"amend the commit body to `Refs #{num}`"
                )
            if not causes:
                causes.append(
                    "an undetermined source outside the PR body — inspect the "
                    "commit history and linked references"
                )
            location = (
                f"PR#{pr_number}:commit:{shas[0][:8]}" if shas
                else f"PR#{pr_number}:body"
            )
            cause_text = "; ".join(f"({i + 1}) {c}" for i, c in enumerate(causes))
            detail = (
                f"PR #{pr_number} will auto-close #{num} on merge "
                f"(closingIssuesReferences) but its body has no affirmative "
                f"`Closes #{num}`. Source(s): {cause_text}. If this PR genuinely "
                f"fully closes #{num}, instead add `Closes #{num}` to the PR "
                f"body and advance the issue label first; if it is a "
                f"partial/umbrella step, apply ALL fixes above so the "
                f"auto-close does not fire."
            )
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=location,
                    detail=detail,
                    fix_hint_ref=getattr(_RULE, "fix_hint_ref", None),
                )
            )
            log.error(
                "%s: PR #%s auto-closes #%s without affirmative body Closes "
                "(negated=%s, commits=%s)",
                _RULE.rule_id, pr_number, num, num in negated, shas,
                extra={"pr": pr_number, "issue": num, "rule_id": _RULE.rule_id},
            )

    return violations


def scan_open_prs_for_closes_keyword_discipline(
    repo_root: Optional[Path] = None,
) -> List[Violation]:
    """End-to-end scanner: fetch open PRs + commits, emit Violations."""
    root = repo_root or REPO_ROOT
    mgr = PRManager(target_dir=root)
    records: List[dict] = []
    for pr in mgr.fetch_open_prs():
        pr_number = pr.get("number")
        if not pr_number:
            continue
        closing_refs = [
            ref.get("number")
            for ref in (pr.get("closingIssuesReferences") or [])
            if ref.get("number")
        ]
        records.append(
            {
                "pr_number": pr_number,
                "body": pr.get("body") or "",
                "commits": mgr.fetch_pr_commits(pr_number),
                "closing_refs": closing_refs,
            }
        )
    return evaluate_closes_keyword_violations(records)


# ---------------------------------------------------------------------------
# Unit tests — pure evaluator, synthetic fixtures (no network)
# ---------------------------------------------------------------------------


def test_evaluator_flags_commit_injected_close():
    """The #927 bite: body uses Refs #N, a commit message uses Closes #N."""
    records = [
        {
            "pr_number": 927,
            "body": "Refs #919\n\nDelivers Sections B and C only.",
            "commits": [
                {"sha": "deadbeef1234", "message": "Closes #919 Sections B and C"},
            ],
            "closing_refs": [919],
        }
    ]
    violations = evaluate_closes_keyword_violations(records)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule_id == "coach.pr.closes-keyword-discipline"
    assert "919" in v.detail
    assert "deadbeef" in v.location or "deadbeef" in v.detail


def test_evaluator_flags_negated_body_close():
    """The 'Does NOT close #N still fires auto-close' bite.

    GitHub registered #321 as a closing reference despite the body's
    negation, so the close is real and must be flagged.
    """
    records = [
        {
            "pr_number": 500,
            "body": "This PR does not close #321 — follow-up tracked separately.",
            "commits": [],
            "closing_refs": [321],
        }
    ]
    violations = evaluate_closes_keyword_violations(records)
    assert len(violations) == 1
    assert violations[0].rule_id == "coach.pr.closes-keyword-discipline"
    assert "321" in violations[0].detail
    assert "negat" in violations[0].detail.lower()
    assert violations[0].location == "PR#500:body"


def test_evaluator_enumerates_all_causes_for_one_issue():
    """The real #927 shape: negated body keyword AND a commit Closes — both
    point at the same issue, so ONE violation must list BOTH causes (fixing
    only one leaves the auto-close firing)."""
    records = [
        {
            "pr_number": 927,
            "body": "Refs #919\n\nThis PR does **NOT** close #919 — Sections B+C only.",
            "commits": [
                {"sha": "fd04793dcafe", "message": "stuff (#919 B+C)\n\nCloses #919 Sections"},
            ],
            "closing_refs": [919],
        }
    ]
    violations = evaluate_closes_keyword_violations(records)
    assert len(violations) == 1
    detail = violations[0].detail.lower()
    assert "negat" in detail            # body cause enumerated
    assert "fd04793d" in violations[0].detail  # commit cause enumerated
    assert "commit" in detail


def test_evaluator_ignores_harmless_negated_mention_not_autoclosed():
    """A 'does not close #N' body mention that GitHub did NOT register (not in
    closing_refs) is harmless — no false positive."""
    records = [
        {
            "pr_number": 600,
            "body": "Note: this does not close #777; tracked separately.",
            "commits": [],
            "closing_refs": [],
        }
    ]
    assert evaluate_closes_keyword_violations(records) == []


def test_evaluator_passes_clean_full_close():
    """Body affirmatively closes #N and that matches closingIssuesReferences."""
    records = [
        {
            "pr_number": 100,
            "body": "Closes #100\n\n## Issue Metadata\n...",
            "commits": [
                {"sha": "abc123", "message": "feat: do the thing\n\nCloses #100"},
            ],
            "closing_refs": [100],
        }
    ]
    # A commit keyword is tolerated when the body affirmatively declares the
    # same close — the body is the source of truth and the two agree.
    assert evaluate_closes_keyword_violations(records) == []


def test_evaluator_passes_refs_only_no_autoclose():
    """Body uses Refs #N, no closing keyword anywhere, no auto-close."""
    records = [
        {
            "pr_number": 101,
            "body": "Refs #200\n\nPartial step toward the umbrella.",
            "commits": [
                {"sha": "def456", "message": "chore: partial step\n\nRefs #200"},
            ],
            "closing_refs": [],
        }
    ]
    assert evaluate_closes_keyword_violations(records) == []


def test_evaluator_handles_empty_and_missing_fields():
    """Defensive: empty record list and sparse records do not raise."""
    assert evaluate_closes_keyword_violations([]) == []
    assert evaluate_closes_keyword_violations([{}]) == []
    assert evaluate_closes_keyword_violations([{"pr_number": 1}]) == []


# ---------------------------------------------------------------------------
# Gate — live scan of every open PR
# ---------------------------------------------------------------------------


def test_no_unintended_closes_keyword_in_open_prs():
    """
    SPEC: ``pr.convention.yaml::rules[coach.pr.closes-keyword-discipline]``.

    Given:  Every open PR's body, commit messages, and GraphQL
            ``closingIssuesReferences``.
    When:   Comparing the set of issues GitHub will auto-close against the
            set the PR body affirmatively declares (and scanning for negated
            body keywords).
    Then:   The two agree and no negated keyword exists. Divergences — a
            commit-injected close, or a ``Does NOT close #N`` body phrase the
            parser mishandles — surface as structured ``Violation`` records
            the disposition gate fails on. Strict disposition: bypass forbidden.
    """
    violations = scan_open_prs_for_closes_keyword_discipline(REPO_ROOT)
    assert_disposition_satisfied(
        validator_id=_VALIDATOR_ID,
        violations=violations,
    )


__all__ = [
    "evaluate_closes_keyword_violations",
    "scan_open_prs_for_closes_keyword_discipline",
    "test_no_unintended_closes_keyword_in_open_prs",
]
