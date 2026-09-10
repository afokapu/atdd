# URN: test:govern-lifecycle:placeholder-detection-is-line-anchored:E078-UNIT-001-a-mention-is-not-a-placeholder
# Acceptance: acc:govern-lifecycle:E078-UNIT-001-a-mention-is-not-a-placeholder
# WMBT: wmbt:govern-lifecycle:E078
# Phase: GREEN
# Layer: backend.unit
"""E078-UNIT-001 — a mention of a placeholder is not an unfilled placeholder (#1904).

`check_placeholders` asked `if placeholder in text` over a whole section, so any
prose containing the substring was reported as scaffolding the author forgot to
replace. Its own docstring claimed the opposite — "only placeholder strings that
literally appear in the body are flagged. This avoids regex false positives on
user content" — which describes the intent, not the implementation.

Measured across 120 open atdd-issues before the fix: four hits, zero genuine.

    DEFINE = "define"      # find the JTBD main job     <- 'JTBD' contains 'TBD'
    | 9 | Which predecessor is the pilot? | TBD — chosen before RED
    honestly-broken values (`TBD` 34, `none` 14, `N/A` 7)
    34  TBD                                             <- a count OF TBDs

The first is decisive. The second is worse than harmless: a Decisions table
recording a pending decision is that table working, and the check punished it.

Both directions are asserted here. A detector that stops false-positiving by
detecting nothing is a different defect, and a quieter one.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.issue_template import check_placeholders

# Verbatim from the four issues that blocked every open PR.
REAL_PROSE = [
    ('## Context', 'DEFINE = "define"      # find the JTBD main job'),
    ('## Decisions', '| 9 | Which predecessor is the pilot? | TBD — chosen before RED, recorded here |'),
    ('## Notes', 'honestly-broken values (`TBD` 34, `none` 14, `N/A` 7) *will* be repaired.'),
    ('## Context', '| rows with no binding | 34  TBD |'),
]


@pytest.mark.parametrize("heading,line", REAL_PROSE)
def test_prose_mentioning_a_placeholder_is_not_flagged(heading: str, line: str) -> None:
    assert check_placeholders(f"{heading}\n{line}\n") == []


def test_jtbd_specifically(  ) -> None:
    """Named on its own because it is the clearest proof the match was textual:
    'JTBD' is a word, and 'TBD' is inside it."""
    assert check_placeholders("## Context\nfind the JTBD main job\n") == []


@pytest.mark.parametrize("line", ["TBD", "  TBD  ", "_TBD_", "`TBD`", "- TBD", "*TBD*"])
def test_a_bare_placeholder_line_is_still_flagged(line: str) -> None:
    """THE OTHER DIRECTION. The template ships several placeholders already
    wrapped in emphasis, and an author who leaves `_TBD_` has still left it."""
    assert check_placeholders(f"## Context\n{line}\n") == [("## Context", "TBD")]


def test_a_parenthesised_placeholder_is_still_flagged() -> None:
    assert check_placeholders("## Notes\n(none yet)\n") == [("## Notes", "(none yet)")]


def test_a_filled_section_is_clean() -> None:
    body = "## Context\nThe registry reader globbed sidecars, so `--train _aliases` resolved.\n"
    assert check_placeholders(body) == []


def test_the_detector_still_detects_something() -> None:
    """Guards against the fix that passes by never firing."""
    assert check_placeholders("## Context\nTBD\n"), (
        "the detector no longer reports a placeholder that is plainly unfilled"
    )
