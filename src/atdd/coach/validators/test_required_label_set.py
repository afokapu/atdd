"""
Assert every ``atdd-issue``-labeled open issue carries the label families that
something actually reads: one ``atdd:<PHASE>``.

Originally #296 D006 required a TRIPLET — phase, ``archetype:*`` and ``wagon:*``.
#1761 dropped the latter two: neither has a reader, and the issue schema can no
longer express a Wagon row at all. See ``_missing_label_families`` for the
measurements.

WMBT covered:
- wmbt:govern-lifecycle:D006 — acc:govern-lifecycle:D006-UNIT-001-require-only-the-label-families-with-a-reader

Why this validator exists
-------------------------
Labels drift when humans edit them manually and when a phase transition
partially fails, and nothing re-checks afterwards. The issue body metadata is
the source of truth; the label set must mirror it.

The original rationale said "``atdd issue <slug>`` applies the full triplet on
creation" — that command was removed in #1309, and its replacement
``atdd author issue`` applies ``atdd-issue`` and ``atdd:<phase>`` only. The
premise expired with the command; the concern for the read families did not.

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

def _phase_labels() -> Tuple[str, ...]:
    """The phase labels, DERIVED from the phase machine rather than restated.

    This was a hardcoded tuple of eight, and the machine declares nine — it had
    drifted, missing OBSOLETE, so every retired issue was reported as lacking a
    phase label while visibly carrying `atdd:OBSOLETE`. The docstring claimed the
    set was "pinned to the label taxonomy schema"; it was pinned to nothing.

    phase_machine.convention.yaml is the single source of truth for the lifecycle
    — "add or change a phase HERE, never in Python" — so this reads it. A phase
    added there is covered by construction, and this cannot drift again.
    """
    from atdd.coach.gate.phase_edges import phase_machine

    return tuple(f"atdd:{phase}" for phase in sorted(phase_machine()))


_PHASE_LABELS: Tuple[str, ...] = _phase_labels()


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
    - ``atdd:<PHASE>`` — exactly one from the canonical phase set.

    ``archetype:*`` AND ``wagon:*`` WERE REQUIRED HERE and are not any more
    (#1761). Neither had a reader:

    - ``archetype:*`` has exactly two read sites in the whole repository, and
      both are circular — ``sync_labels``' own "is this label mine to manage?"
      guard (``issue.py:685``) and this function. Nothing filters by it, no gh
      query names it, no workflow reads it.
    - ``wagon:*`` was not merely unread but UNSATISFIABLE: the issue template
      emits no ``Wagon`` row since the field became train + feature (#1477), so
      ``_derive_expected_labels`` can never produce one and no issue authored
      through the sanctioned path can carry it.

    Requiring them made all 100 correctly-authored issues non-compliant, which is
    the state a check reaches just before people stop reading it.
    """
    missing: List[str] = []
    if not any(label in _PHASE_LABELS for label in labels):
        missing.append("atdd:<PHASE>")
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
def test_atdd_issues_carry_the_label_families_with_a_reader(github_issues):
    """D006: Every ``atdd-issue``-labeled open issue must carry one
    ``atdd:<PHASE>`` label.

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
            + "\n\nFix: `atdd coach sync-labels <N>` reads body metadata "
            "(Archetypes, Wagon, Status rows) and applies the derived "
            "label set idempotently."
        )


# ---------------------------------------------------------------------------
# Unit tests for the pure helpers — no GitHub API required.
# ---------------------------------------------------------------------------


def test_missing_families_reports_the_phase_when_only_atdd_issue_present():
    """An issue carrying only ``atdd-issue`` is missing its phase — and only that."""
    missing = _missing_label_families([_ISSUE_LABEL])
    assert missing == ["atdd:<PHASE>"]


def test_missing_families_does_not_demand_archetype_or_wagon(): 
    """The shape EVERY sanctioned mint produces must be compliant (#1761).

    `atdd author issue` writes `atdd-issue` and `atdd:<phase>` and nothing else.
    While archetype:* and wagon:* were required, every correctly-authored issue
    was non-compliant — 100 of them — for two families no code reads and one of
    which the issue schema can no longer even express.
    """
    assert _missing_label_families([_ISSUE_LABEL, "atdd:INIT"]) == []


def test_missing_families_accepts_any_valid_phase_label():
    """Any of the canonical phase labels satisfies the PHASE family."""
    for phase in _PHASE_LABELS:
        missing = _missing_label_families([_ISSUE_LABEL, phase])
        assert missing == [], f"{phase} should satisfy atdd:<PHASE> family"


def test_missing_families_empty_for_a_complete_label_set():
    """`atdd-issue` plus a phase is compliant."""
    assert _missing_label_families([_ISSUE_LABEL, "atdd:INIT"]) == []


def test_missing_families_tolerates_the_retired_families_when_present():
    """76 issues still carry archetype:* / wagon:* from before the retirement.

    Dropping the REQUIREMENT must not turn their presence into a complaint —
    this validator reports what is missing, never what is surplus, and
    sync_labels leaves labels outside its scheme alone.
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
        "labels": [{"name": _ISSUE_LABEL}],   # atdd-issue, but no phase
    }]
    drift = _find_issues_missing_required_labels(issues)
    assert len(drift) == 1
    assert "#291" in drift[0]
    assert "atdd:<PHASE>" in drift[0]
    # The retired families must not reappear in the message: naming a family the
    # operator cannot satisfy is how the previous version taught people to skip
    # reading it (#1761).
    assert "archetype:*" not in drift[0]
    assert "wagon:*" not in drift[0]
