# URN: test:author-atdd-substrate:author-issue-body:E010-UNIT-002-no-literal-date-survives-in-the-generator
# Acceptance: acc:author-atdd-substrate:E010-UNIT-002-no-literal-date-survives-in-the-generator
# WMBT: wmbt:author-atdd-substrate:E010
# Phase: RED
# Layer: application
"""E010-UNIT-002 — no date in the emitted body is frozen into the generator.

UNIT-001 pins the Metadata Date row. This pins the SHAPE of the regression
across the WHOLE body: with the clock frozen, every ISO date the generator emits
must equal the frozen day. A literal anywhere — the Date row, the Activity Log
entry, or a section added later — fails here and is named with its value.

Behavioural rather than source-scanning on purpose: it cannot be evaded by
moving the literal, reformatting it, or building it from parts.
"""
from __future__ import annotations

import datetime
import re

from ._helpers import get_create_issue_body, sample_spec

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_FROZEN = datetime.date(2031, 3, 17)


class _FrozenDate(datetime.date):
    @classmethod
    def today(cls) -> datetime.date:
        return _FROZEN


def test_e010_unit_002_no_literal_date_survives_in_the_generator(monkeypatch):
    from atdd.planner.commands import author_issue

    monkeypatch.setattr(author_issue, "date", _FrozenDate, raising=False)

    body = get_create_issue_body()(sample_spec())

    frozen = _FROZEN.isoformat()
    stale = sorted({d for d in _ISO.findall(body) if d != frozen})

    assert stale == [], (
        "the generator emits date(s) that do not move with the clock, so every minted "
        f"issue reports them verbatim: {stale}. Interpolate from date.today() the way "
        "every other Metadata row already does."
    )
