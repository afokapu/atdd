# URN: test:project-shared-state:mint-object-identity:Y002-UNIT-004-shared-h1-parser-pins-commonmark-edges
# Acceptance: acc:project-shared-state:Y002-UNIT-004-shared-h1-parser-pins-commonmark-edges
# WMBT: wmbt:project-shared-state:Y002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: Pin the CommonMark edge cases on which a second, independently-written H1 parser diverged from this one, so the duplication the #1652 orchestrator ruled against cannot silently reopen. Refs #1653, #1654.
"""The shared H1 parser's contract, pinned at the edges (Y002-UNIT-004).

wagon: project-shared-state | feature: mint-object-identity | phase: RED
WMBT: wmbt:project-shared-state:Y002

**Why this file exists.** #1653 and #1654 each independently wrote a fence-aware
H1 parser into ``atdd.state`` — ``body_heading`` and ``issue_title`` — within the
same minute, each unaware of the other. The #1652 orchestrator kept this one and
had the other deleted and rebuilt on top of it. These are the four inputs on
which the two disagreed.

**The live corpus could not have caught any of them.** Over all 825 live bodies
the two parsers agreed exactly. The divergence is latent: no body uses a closing
``#`` sequence *yet*. So the regression guard has to be these literals, not the
corpus.

The first case is the load-bearing one. CommonMark says a trailing ATX closing
sequence is not part of the heading text. If a reader disagreed with this
module's writer about that, then ``rename --title Title`` would write ``# Title #``
and #1654's consistency check would read ``"Title #"``, report a disagreement
with ``data.title == "Title"``, and we would ship the exact defect this program
exists to end — one layer further down.

Hence the round-trip assertion on every case: whatever :func:`retitle_h1` writes,
:func:`first_h1` must read back as exactly the title that was written. That
property, not the spelling of any single heading, is what makes a consistency
check built on this module sound.

This module owns *reading and rewriting* a heading. The ``title_violations``
predicate built on top of it — including its rule that a ``None`` title skips —
belongs to #1654 and is deliberately not implemented here.
"""
from __future__ import annotations

import pytest

from atdd.state.body_heading import first_h1, has_h1, retitle_h1

#: A fence opened with four backticks is not closed by a three-backtick run
#: (CommonMark: the closer must be at least as long as the opener). A parser
#: that closed it early would read ``# not a heading`` — or, having consumed the
#: fence state wrongly, read nothing at all.
FOUR_BACKTICK_FENCE = "````\n```\n# not a heading\n````\n\n# RealTitle\n"

#: ``(label, body, expected_heading)`` — the four inputs the two parsers split on.
DIVERGENT_CASES = (
    pytest.param("# Title #\n", "Title", id="atx-closing-sequence-single"),
    pytest.param("# Title ###\n", "Title", id="atx-closing-sequence-multiple"),
    pytest.param("#\n", "", id="empty-h1-is-present-not-absent"),
    pytest.param(FOUR_BACKTICK_FENCE, "RealTitle", id="longer-fence-encloses-shorter"),
)


@pytest.mark.parametrize("body,expected", DIVERGENT_CASES)
def test_y002_unit_004_reads_the_commonmark_heading(body, expected) -> None:
    """The heading text excludes any closing sequence, and an empty H1 is present."""
    assert first_h1(body) == expected
    # An empty heading reads as "" — falsy, but emphatically *not* absent. A
    # parser that conflated the two would report "no H1" and skip the rewrite.
    assert has_h1(body) is True


@pytest.mark.parametrize("body,expected", DIVERGENT_CASES)
def test_y002_unit_004_rewritten_heading_reads_back_exactly(body, expected) -> None:
    """Round-trip: what retitle_h1 writes, first_h1 reads back as the written title.

    This is the property a consistency check can rest on. Without it, the writer
    and the reader can each be self-consistent and still disagree with each other.
    """
    rewritten = retitle_h1(body, "NewTitle")

    assert first_h1(rewritten) == "NewTitle"
    # The rewrite is confined to the heading line — line count is unchanged and
    # every non-heading line survives byte-for-byte.
    assert len(rewritten.splitlines()) == len(body.splitlines())
    original_lines = body.splitlines()
    for index, line in enumerate(rewritten.splitlines()):
        if first_h1(original_lines[index] + "\n") is None:
            assert line == original_lines[index]


def test_y002_unit_004_a_shorter_run_inside_a_longer_fence_is_not_a_heading() -> None:
    """The enclosed `# not a heading` is never read, and survives a rewrite untouched."""
    assert first_h1(FOUR_BACKTICK_FENCE) == "RealTitle"

    rewritten = retitle_h1(FOUR_BACKTICK_FENCE, "NewTitle")

    assert "# not a heading" in rewritten
    assert rewritten.startswith("````\n```\n# not a heading\n````\n")
