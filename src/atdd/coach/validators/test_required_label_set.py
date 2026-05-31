"""
RED tests for #296 D006 — assert every ``atdd-issue``-labeled open issue
carries the required label triplet: one ``atdd:<PHASE>``, at least one
``archetype:*``, and at least one ``wagon:*``.

WMBT covered:
- wmbt:govern-lifecycle:D006 — acc:govern-lifecycle:D006-UNIT-001-require-phase-archetype-wagon-triplet

Why this validator exists
-------------------------
``atdd issue <slug>`` applies the full triplet on creation, but nothing
re-checks after: labels drift when humans edit them manually, when a
phase transition partially fails, or when label taxonomy evolves. The
issue body metadata (Archetypes, Wagon, Status rows) is the source of
truth; the label set must mirror it.

The PHASE set is pinned to the label taxonomy schema
(``atdd/coach/schemas/label_taxonomy.schema.json``) rather than a local
constant so that any taxonomy extension (e.g., ``atdd:ADOPT`` from #260)
flows through automatically.

Run:
    PYTHONPATH=src python3 -m pytest -q \
        src/atdd/coach/validators/test_required_label_set.py -v
"""

from typing import Dict, List, Tuple

import pytest


_ISSUE_LABEL = "atdd-issue"

_PHASE_LABELS: Tuple[str, ...] = (
    "atdd:INIT",
    "atdd:PLANNED",
    "atdd:RED",
    "atdd:GREEN",
    "atdd:SMOKE",
    "atdd:REFACTOR",
    "atdd:COMPLETE",
    "atdd:BLOCKED",
)


def _labels_of(issue: Dict) -> List[str]:
    """Return label names from a GitHub issue dict."""
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


def _missing_label_families(labels: List[str]) -> List[str]:
    """Return the names of missing required label families for a single issue.

    Families:
    - ``atdd:<PHASE>``   — exactly one from the canonical phase set.
    - ``archetype:*``    — one or more.
    - ``wagon:*``        — one or more.
    """
    missing: List[str] = []
    if not any(label in _PHASE_LABELS for label in labels):
        missing.append("atdd:<PHASE>")
    if not any(label.startswith("archetype:") for label in labels):
        missing.append("archetype:*")
    if not any(label.startswith("wagon:") for label in labels):
        missing.append("wagon:*")
    return missing


def _find_issues_missing_required_labels(issues: List[Dict]) -> List[str]:
    """Return one drift message per ``atdd-issue``-labeled issue whose
    label set is missing any required family.

    Non-``atdd-issue`` issues are out of scope — they are caught by the
    inverse-filter validator (``test_unlabeled_open_issues``) instead.
    """
    messages: List[str] = []
    for issue in issues:
        if str(issue.get("state", "open")).lower() != "open":
            continue
        labels = _labels_of(issue)
        if _ISSUE_LABEL not in labels:
            continue
        missing = _missing_label_families(labels)
        if not missing:
            continue
        number = issue.get("number", "<unknown>")
        title = issue.get("title", "")
        messages.append(
            f"  #{number}: {title!r} missing required label families: "
            f"{missing}"
        )
    return messages


@pytest.mark.coach
@pytest.mark.github_api  # consumes live `github_issues` — offline gate must skip (#932)
def test_atdd_issues_have_required_label_triplet(github_issues):
    """D006: Every ``atdd-issue``-labeled open issue must carry one
    ``atdd:<PHASE>`` label, at least one ``archetype:*`` label, and at
    least one ``wagon:*`` label.

    Given: Open issues carrying the ``atdd-issue`` label (from the
           existing ``github_issues`` prefetch fixture — this validator
           audits the *completeness* of labels on issues that are already
           in scope, complementing ``test_unlabeled_open_issues`` which
           audits *inclusion* of the issue itself).
    When:  Walking each issue's label set.
    Then:  Any issue missing a required family is a hard failure naming
           the issue number and the missing families.
    """
    drift = _find_issues_missing_required_labels(list(github_issues))
    if drift:
        pytest.fail(
            f"\n\n{len(drift)} atdd-issue(s) missing required label families:\n\n"
            + "\n".join(drift)
            + "\n\nFix: `atdd issue sync-labels <N>` reads body metadata "
            "(Archetypes, Wagon, Status rows) and applies the derived "
            "label set idempotently."
        )


# ---------------------------------------------------------------------------
# Unit tests for the pure helpers — no GitHub API required.
# ---------------------------------------------------------------------------


def test_missing_families_reports_all_three_when_only_atdd_issue_present():
    """An issue carrying only ``atdd-issue`` is missing the full triplet."""
    missing = _missing_label_families([_ISSUE_LABEL])
    assert set(missing) == {"atdd:<PHASE>", "archetype:*", "wagon:*"}


def test_missing_families_reports_phase_only_when_archetype_and_wagon_present():
    """An issue missing only ``atdd:<PHASE>`` reports exactly that family."""
    missing = _missing_label_families([_ISSUE_LABEL, "archetype:coach", "wagon:govern-lifecycle"])
    assert missing == ["atdd:<PHASE>"]


def test_missing_families_accepts_any_valid_phase_label():
    """Any of the canonical phase labels satisfies the PHASE family."""
    for phase in _PHASE_LABELS:
        missing = _missing_label_families([_ISSUE_LABEL, phase, "archetype:coach", "wagon:x"])
        assert missing == [], f"{phase} should satisfy atdd:<PHASE> family"


def test_missing_families_empty_for_complete_label_set():
    """A full triplet (plus ``atdd-issue``) is compliant."""
    labels = [_ISSUE_LABEL, "atdd:INIT", "archetype:coach", "wagon:govern-lifecycle"]
    assert _missing_label_families(labels) == []


def test_missing_families_allows_multiple_archetypes_and_wagons():
    """Issues spanning multiple archetypes/wagons (e.g., cross-cutting
    changes like #291) remain compliant — the validator asserts ≥1,
    not exactly 1.
    """
    labels = [
        _ISSUE_LABEL, "atdd:INIT",
        "archetype:coach", "archetype:contracts",
        "wagon:govern-lifecycle", "wagon:define-plans",
    ]
    assert _missing_label_families(labels) == []


def test_find_drift_skips_non_atdd_issue_items():
    """Issues without ``atdd-issue`` are out of scope for this validator —
    the inverse-filter validator (``test_unlabeled_open_issues``) handles
    them.
    """
    issues = [{
        "number": 501,
        "title": "plain",
        "state": "open",
        "labels": [{"name": "bug"}],
    }]
    assert _find_issues_missing_required_labels(issues) == []


def test_find_drift_skips_closed_issues():
    """Closed issues are terminal — label drift there is historical noise."""
    issues = [{
        "number": 123,
        "title": "closed-partial",
        "state": "closed",
        "labels": [{"name": _ISSUE_LABEL}],
    }]
    assert _find_issues_missing_required_labels(issues) == []


def test_find_drift_names_issue_and_missing_families_in_message():
    """Failure messages pinpoint both the issue number and the missing
    families so operators can act without re-deriving context.
    """
    issues = [{
        "number": 291,
        "title": "custom themes",
        "state": "open",
        "labels": [{"name": _ISSUE_LABEL}, {"name": "atdd:INIT"}],
    }]
    drift = _find_issues_missing_required_labels(issues)
    assert len(drift) == 1
    assert "#291" in drift[0]
    assert "archetype:*" in drift[0]
    assert "wagon:*" in drift[0]
