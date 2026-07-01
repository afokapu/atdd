# URN: test:govern-lifecycle:state:E059-UNIT-001-breaking-change-detected-only-as-a-conventional-commit-footer
# Acceptance: acc:govern-lifecycle:E059-UNIT-001-breaking-change-detected-only-as-a-conventional-commit-footer
# WMBT: wmbt:govern-lifecycle:E059
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E059-UNIT-001 — BREAKING CHANGE escalates to MAJOR only as a real footer.

#1297. The first real Publish run (28495533869) bumped 3.151.0 -> 4.0.0 because
``change_class_for_commit`` matched the bare substring ``BREAKING CHANGE``
anywhere in the message — and the #1285/#1291 merge commit's body merely
*describes* the mapping (``...breaking !/BREAKING CHANGE=MAJOR, else PATCH``).
Per the Conventional Commits spec, a breaking change is signalled by a ``type!:``
marker OR a line-anchored ``BREAKING CHANGE:`` / ``BREAKING-CHANGE:`` footer — NOT
a prose mention. This test pins that: a prose mention on a ``feat`` classifies
MINOR, while a genuine footer and a ``!`` marker still classify MAJOR.
"""
from __future__ import annotations

import pytest

from atdd.state import version as ver


# The load-bearing regression: a feat whose body mentions the phrase in prose
# (not a colon-terminated footer at a line start) must NOT escalate to MAJOR.
def test_prose_mention_of_breaking_change_on_a_feat_is_minor_not_major():
    msg = (
        "feat(atdd): wire release worker\n\n"
        "change_class_for_commit maps a type to PATCH/MINOR/MAJOR "
        "(feat=MINOR, breaking !/BREAKING CHANGE=MAJOR, else PATCH)."
    )
    assert ver.change_class_for_commit(msg) == "MINOR"


@pytest.mark.parametrize(
    "message, expected",
    [
        # Genuine footers — still MAJOR.
        ("feat(atdd): add a flag\n\nBREAKING CHANGE: the old flag is gone", "MAJOR"),
        ("fix: tighten a guard\n\nBREAKING-CHANGE: drops a public return", "MAJOR"),
        # `type!:` marker — still MAJOR.
        ("feat(atdd)!: remove the deprecated flag", "MAJOR"),
        ("fix!: drop a public API", "MAJOR"),
        # Prose mentions that are NOT footers — classify by type.
        ("feat: mentions BREAKING CHANGE in a sentence", "MINOR"),
        ("fix: note about a breaking change=major mapping", "PATCH"),
        # Plain conventional types — unchanged.
        ("feat(atdd): add X", "MINOR"),
        ("chore(atdd): bump deps", "PATCH"),
    ],
)
def test_breaking_change_only_from_footer_or_bang_marker(message, expected):
    assert ver.change_class_for_commit(message) == expected
