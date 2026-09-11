# URN: test:define-plans:atdd-plan-session:E002-UNIT-001-corpus-drift-is-detected
# Acceptance: acc:define-plans:E002-UNIT-001-corpus-drift-is-detected
# WMBT: wmbt:define-plans:E002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E002-UNIT-001 — verb-object drift already on disk is detected and reported.

`planner.wagon.name-is-verb-object` and `planner.feature.name-is-verb-object`
gate the AUTHORING path: `confirm_naming` reads `session.kept_units()`, so
anything authored through `atdd plan` conforms by construction. Neither looks at
the corpus. An artifact renamed by hand, or created before the rules existed,
drifts with nothing to notice.

This is the unit contract for the scanner that closes that gap. It asserts three
things, and the third is the one that makes the report useful rather than a
number: a noun-led name and an `and`-connective name are DIFFERENT findings with
different remedies — the first is renamed, the second may mean the artifact does
two jobs.

The scanner reports; it never blocks. Its disposition is advisory because 101 of
229 authored artifacts do not conform and renaming one wagon touches ~54 files.
"""
from __future__ import annotations

import pytest

from atdd.planner.validators.verb_object_corpus import scan_names

pytestmark = [pytest.mark.planner]


def test_a_noun_led_name_is_reported_with_its_reason():
    findings = scan_names([("wagon", "coach-ops")])
    assert len(findings) == 1
    assert findings[0].slug == "coach-ops"
    assert findings[0].artifact_kind == "wagon"
    assert findings[0].cause == "leading-token-not-a-verb"
    assert "coach" in findings[0].reason


def test_a_verb_object_name_is_not_reported():
    assert scan_names([("wagon", "author-artifacts"),
                       ("feature", "enforce-conventions")]) == []


def test_an_and_connective_is_a_distinct_cause_from_a_noun_lead():
    findings = {f.slug: f.cause for f in scan_names([
        ("wagon", "observe-and-correct"),   # leads with a verb, carries `and`
        ("wagon", "security-patterns"),     # leads with a noun
    ])}
    assert findings["observe-and-correct"] == "connective"
    assert findings["security-patterns"] == "leading-token-not-a-verb"


def test_the_scanner_reads_the_same_lexicon_as_the_authoring_gate():
    """A name the Ratify gate accepts must never be reported as drift, or the two
    halves disagree about what a verb is."""
    from atdd.planner.naming import is_verb_object

    for slug in ("author-artifacts", "place-worktrees", "review-phase-boundaries"):
        assert is_verb_object(slug, artifact="wagon")[0], f"gate rejects {slug}"
        assert scan_names([("wagon", slug)]) == [], f"scanner reports {slug}"
