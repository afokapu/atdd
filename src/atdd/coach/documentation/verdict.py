"""The verdict vocabulary at the documentation capability seam.

CORE OWNS THESE FOUR LITERALS. The shipped `atdd.extension.planner.docs` carries a
note at the head of its own `verdict.py`:

    >>> OPEN SEAM — CROSS-CHECK WITH THE CORE UNIT. If core exposes a shared
    >>> vocabulary module, this module must DELEGATE to it rather than keep its own
    >>> copies. The wire values must be these four literals either way; that is the
    >>> part the two units agree on and the part a drift would break.

This module is that core vocabulary. It is the side of the agreement core owns, and
the extension's copies are meant to collapse into it.

They are plain strings and not an enum ON PURPOSE. Spec 2 §3 forbids importing
``GateVerdict`` from ``atdd.coach.gate`` into the documentation domain AND forbids
defining a second enum (#1772 Decisions 16-18, #1774). A string vocabulary in one
module satisfies both: nothing re-implements core's meanings, because there is one
place they are written down.

THE DISTINCTION THAT MATTERS. ``NOT_APPLICABLE`` and ``COULD_NOT_CHECK`` must never
collapse into one another. *There is no obligation here* and *I could not see whether
the obligation was met* are different facts, and this repository has already merged
them in at least three places: #1745 (a lookup failure reported as a pass), #1774
("no mirror found" read as "nothing to lose"), #1716 (checks that pass when they
cannot observe). An unresolvable lookup stays DATA — named, reportable, reaching the
report — never an empty clean result.
"""
from __future__ import annotations

#: Obligation discharged. Permits.
PASS = "PASS"
#: Declared and demonstrably not discharged, or the capability crashed/timed out/raised. BLOCKS.
FAIL = "FAIL"
#: Genuinely nothing to check — no capability installed, or `impact: none` with a reason. Permits.
NOT_APPLICABLE = "NOT_APPLICABLE"
#: Ran to completion but could not answer. BLOCKS.
COULD_NOT_CHECK = "COULD_NOT_CHECK"

#: Every wire value, in precedence order for reporting.
ALL = (FAIL, COULD_NOT_CHECK, NOT_APPLICABLE, PASS)

#: The two that refuse a transition. Membership, not a boolean flag on each verdict,
#: so adding a fifth verdict forces a decision here rather than defaulting to permit.
_BLOCKING = frozenset({FAIL, COULD_NOT_CHECK})


def blocks(value: str) -> bool:
    """Whether this verdict refuses the transition.

    An unknown verdict blocks. A vocabulary this module does not recognise is itself
    an unobserved state, and permitting on it would be the same fail-open the
    COULD_NOT_CHECK/NOT_APPLICABLE split exists to prevent.
    """
    if value not in ALL:
        return True
    return value in _BLOCKING
