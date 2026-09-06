# URN: test:author-atdd-substrate:author-issue-body:E010-UNIT-002-no-literal-date-survives-in-the-generator
# Acceptance: acc:author-atdd-substrate:E010-UNIT-002-no-literal-date-survives-in-the-generator
# WMBT: wmbt:author-atdd-substrate:E010
# Phase: RED
# Layer: application
"""E010-UNIT-002 — no literal ISO date survives in the generator's Date row.

UNIT-001 pins today's behaviour; this pins the SHAPE of the regression. A future
edit that reintroduces a frozen literal — any literal, not just 2026-06-29 —
fails here with the offending line named, so the fix location is unambiguous.
"""
from __future__ import annotations

import inspect
import re

_ISO_LITERAL = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_ROW = re.compile(r"\|\s*Date\s*\|")


def test_e010_unit_002_no_literal_date_survives_in_the_generator():
    from atdd.planner.commands import author_issue

    source = inspect.getsource(author_issue)

    offenders = [
        (lineno, line.strip())
        for lineno, line in enumerate(source.splitlines(), start=1)
        if _DATE_ROW.search(line) and _ISO_LITERAL.search(line)
    ]

    assert offenders == [], (
        "the Metadata Date row is assembled from a hardcoded date literal, so every "
        "minted issue reports the same day:\n"
        + "\n".join(
            f"  {author_issue.__file__}:{lineno}: {text}" for lineno, text in offenders
        )
    )
