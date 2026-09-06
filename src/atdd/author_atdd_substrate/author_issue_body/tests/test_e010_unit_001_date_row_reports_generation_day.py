# URN: test:author-atdd-substrate:author-issue-body:E010-UNIT-001-date-row-reports-generation-day
# Acceptance: acc:author-atdd-substrate:E010-UNIT-001-date-row-reports-generation-day
# WMBT: wmbt:author-atdd-substrate:E010
# Phase: RED
# Layer: application
"""E010-UNIT-001 — the Metadata Date row reports the day the body is generated.

Every other row in the Metadata table is interpolated from the spec. Date alone
was a literal, so every issue ever minted claimed the same day. Freezing the
clock the generator reads must move the Date row with it.
"""
from __future__ import annotations

import datetime
import re

from ._helpers import get_create_issue_body, get_validate_issue_body, sample_spec

_FROZEN = datetime.date(2031, 3, 17)


class _FrozenDate(datetime.date):
    """Stands in for ``datetime.date`` so ``date.today()`` is deterministic."""

    @classmethod
    def today(cls) -> datetime.date:
        return _FROZEN


def _date_row(body: str) -> str | None:
    match = re.search(r"^\|\s*Date\s*\|\s*`([^`]+)`\s*\|\s*$", body, re.MULTILINE)
    return match.group(1) if match else None


def test_e010_unit_001_date_row_reports_generation_day(monkeypatch):
    author_issue = __import__(
        "atdd.planner.commands.author_issue", fromlist=["create_issue_body"]
    )
    monkeypatch.setattr(author_issue, "date", _FrozenDate, raising=False)

    body = get_create_issue_body()(sample_spec())

    row = _date_row(body)
    assert row is not None, "the Metadata table carries no Date row"
    assert row == _FROZEN.isoformat(), (
        f"Date row reports {row!r}, not the generation day {_FROZEN.isoformat()!r} — "
        "the row is not derived from the clock"
    )

    # The row must move with the clock without breaking the schema contract.
    assert get_validate_issue_body()(body) == [], "body stopped being schema-valid"
