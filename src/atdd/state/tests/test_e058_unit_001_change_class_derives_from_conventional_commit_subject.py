# URN: test:govern-lifecycle:state:E058-UNIT-001-change-class-derives-from-conventional-commit-subject
# Acceptance: acc:govern-lifecycle:E058-UNIT-001-change-class-derives-from-conventional-commit-subject
# WMBT: wmbt:govern-lifecycle:E058
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E058-UNIT-001 — change_class_for_commit maps a conventional-commit subject.

#1285 / #1172 §3.1. The post-merge publish job derives the release change class
from the merge commit's conventional-commit type: ``feat`` -> MINOR;
``fix``/``chore``/``docs``/``refactor``/``devops`` (and any unrecognized type)
-> PATCH; a ``type!:`` breaking marker or a ``BREAKING CHANGE`` note -> MAJOR.
"""
from __future__ import annotations

import pytest

from atdd.state import version as ver


@pytest.mark.parametrize(
    "subject, expected",
    [
        ("feat(atdd): add the release worker wiring", "MINOR"),
        ("feat: brand new capability", "MINOR"),
        ("fix(atdd): correct the resolver", "PATCH"),
        ("chore(atdd): bump deps", "PATCH"),
        ("docs: clarify the design doc", "PATCH"),
        ("refactor(state): extract helper", "PATCH"),
        ("devops: tweak CI", "PATCH"),
        ("something totally unconventional", "PATCH"),
        ("feat(atdd)!: remove the deprecated flag", "MAJOR"),
        ("fix!: drop a public API", "MAJOR"),
    ],
)
def test_change_class_for_commit_subject_mapping(subject, expected):
    assert ver.change_class_for_commit(subject) == expected


def test_breaking_change_footer_is_major():
    """A ``BREAKING CHANGE`` note anywhere in the message forces MAJOR even
    when the type is a non-breaking ``feat``/``fix``."""
    msg = "feat(atdd): add a flag\n\nBREAKING CHANGE: the old flag is gone"
    assert ver.change_class_for_commit(msg) == "MAJOR"
