"""
RED tests for #296 D005 — assert every open repo issue carries the
``atdd-issue`` label so coach validators never silently drop
non-compliant issues.

WMBT covered:
- wmbt:govern-lifecycle:D005 — acc:govern-lifecycle:D005-UNIT-001-fail-on-unlabeled-open-issue

Why this validator exists
-------------------------
Every existing coach validator filters by ``atdd-issue`` as a precondition
(see ``conftest.py::github_issues`` — "All open issues with atdd-issue
label"). An issue created outside ``atdd issue <slug>`` (web UI,
``gh issue create``) lands without labels and becomes invisible to every
downstream check: the prefetch cache drops it, and ``atdd validate coach``
returns PASS on a repo state that is demonstrably non-compliant. #291
sat unlabeled from creation until manually audited, and zero validator
flagged it.

This validator inverts the filter: it walks **all** open repo issues
(unfiltered) via the new ``all_open_issues_unfiltered`` fixture, and
fails hard when any one of them is missing ``atdd-issue``.

Run:
    PYTHONPATH=src python3 -m pytest -q \
        src/atdd/coach/validators/test_unlabeled_open_issues.py -v
"""

from typing import Dict, List

import pytest


_REQUIRED_LABEL = "atdd-issue"

# WMBT sub-issues carry ``atdd-wmbt`` instead of ``atdd-issue`` — they are
# first-class ATDD-tracked but a different shape (required_label_set does
# not apply to them). Either label satisfies the "is-ATDD-tracked" check.
_WMBT_LABEL = "atdd-wmbt"
_ATDD_TRACKED_LABELS = frozenset({_REQUIRED_LABEL, _WMBT_LABEL})


def _labels_of(issue: Dict) -> List[str]:
    """Return label names from a GitHub issue dict.

    Accepts both the ``[{name: "..."}, ...]`` REST shape and the flat
    ``["...", ...]`` convenience shape some stubs use.
    """
    raw = issue.get("labels") or []
    out: List[str] = []
    for entry in raw:
        if isinstance(entry, dict):
            name = entry.get("name")
            if name:
                out.append(name)
        elif isinstance(entry, str):
            out.append(entry)
    return out


def _find_unlabeled_open_issues(issues: List[Dict]) -> List[str]:
    """Return one drift message per open issue not tracked by ATDD.

    An issue is "tracked" when it carries either ``atdd-issue`` (parent
    issue) or ``atdd-wmbt`` (WMBT sub-issue). Any other open issue — no
    labels, or labels unrelated to ATDD — is drift.

    Caller must pass **unfiltered** open issues (i.e., do NOT pre-filter
    by the ``atdd-issue`` label — that's the bug this validator exists
    to catch).
    """
    messages: List[str] = []
    for issue in issues:
        if str(issue.get("state", "open")).lower() != "open":
            continue
        labels = _labels_of(issue)
        if any(lbl in _ATDD_TRACKED_LABELS for lbl in labels):
            continue
        number = issue.get("number", "<unknown>")
        title = issue.get("title", "")
        messages.append(f"  #{number}: {title!r} lacks '{_REQUIRED_LABEL}' label")
    return messages


@pytest.mark.coach
def test_no_open_issues_lack_atdd_issue_label(all_open_issues_unfiltered):
    """D005: Every open repo issue must carry the ``atdd-issue`` label so
    it is visible to every coach validator.

    Given: The full set of open GitHub issues in the configured repo,
           unfiltered by label (via the ``all_open_issues_unfiltered``
           fixture that bypasses the default ``atdd-issue`` prefetch
           filter).
    When:  Walking each issue's label set.
    Then:  Any issue missing ``atdd-issue`` is a hard failure, naming the
           issue number and suggesting a remediation command.
    """
    drift = _find_unlabeled_open_issues(list(all_open_issues_unfiltered))
    if drift:
        pytest.fail(
            f"\n\n{len(drift)} open issue(s) lack the '{_REQUIRED_LABEL}' label "
            f"and are invisible to every coach validator:\n\n"
            + "\n".join(drift)
            + "\n\nFix: `atdd issue sync-labels <N>` (preferred, reads body metadata) "
            "or `gh issue edit <N> --add-label atdd-issue` (manual fallback)."
        )


# ---------------------------------------------------------------------------
# Unit tests for the pure helper — no GitHub API required.
# ---------------------------------------------------------------------------


def test_find_unlabeled_flags_issue_with_empty_labels():
    """An open issue with ``labels: []`` is flagged as unlabeled."""
    issues = [{"number": 291, "title": "feat: custom themes", "state": "open", "labels": []}]
    drift = _find_unlabeled_open_issues(issues)
    assert len(drift) == 1
    assert "#291" in drift[0]
    assert _REQUIRED_LABEL in drift[0]


def test_find_unlabeled_flags_issue_missing_atdd_issue_among_other_labels():
    """An open issue carrying other labels but not ``atdd-issue`` is flagged."""
    issues = [{
        "number": 42,
        "title": "rogue issue",
        "state": "open",
        "labels": [{"name": "bug"}, {"name": "needs-triage"}],
    }]
    drift = _find_unlabeled_open_issues(issues)
    assert len(drift) == 1
    assert "#42" in drift[0]


def test_find_unlabeled_ignores_properly_labeled_issue():
    """An open issue carrying ``atdd-issue`` is not flagged."""
    issues = [{
        "number": 296,
        "title": "compliant",
        "state": "open",
        "labels": [{"name": _REQUIRED_LABEL}, {"name": "atdd:INIT"}],
    }]
    assert _find_unlabeled_open_issues(issues) == []


def test_find_unlabeled_ignores_wmbt_sub_issues():
    """WMBT sub-issues carry ``atdd-wmbt`` instead of ``atdd-issue`` —
    they are first-class ATDD-tracked and must not be flagged by the
    inverse-filter validator.
    """
    issues = [{
        "number": 312,
        "title": "wmbt:govern-lifecycle:D005 — ...",
        "state": "open",
        "labels": [{"name": _WMBT_LABEL}],
    }]
    assert _find_unlabeled_open_issues(issues) == []


def test_find_unlabeled_ignores_closed_issues():
    """Closed issues are out of scope — retroactive labeling of closed
    state adds noise without signal.
    """
    issues = [{
        "number": 123,
        "title": "closed-rogue",
        "state": "closed",
        "labels": [],
    }]
    assert _find_unlabeled_open_issues(issues) == []


def test_find_unlabeled_accepts_flat_string_labels_shape():
    """Helper tolerates the ``labels: ["foo", "bar"]`` convenience shape
    used by some stubs and prefetch caches.
    """
    issues = [{
        "number": 7,
        "title": "string-labels",
        "state": "open",
        "labels": ["atdd-issue", "atdd:INIT"],
    }]
    assert _find_unlabeled_open_issues(issues) == []


def test_find_unlabeled_walks_multiple_issues_independently():
    """Drift is reported per issue; compliant issues are not included."""
    issues = [
        {"number": 1, "title": "ok",    "state": "open", "labels": [{"name": "atdd-issue"}]},
        {"number": 2, "title": "rogue", "state": "open", "labels": []},
        {"number": 3, "title": "ok",    "state": "open", "labels": [{"name": "atdd-issue"}]},
        {"number": 4, "title": "rogue", "state": "open", "labels": [{"name": "bug"}]},
    ]
    drift = _find_unlabeled_open_issues(issues)
    assert len(drift) == 2
    assert any("#2" in m for m in drift)
    assert any("#4" in m for m in drift)
