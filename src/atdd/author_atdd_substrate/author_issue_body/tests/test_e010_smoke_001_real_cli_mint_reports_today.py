# URN: test:author-atdd-substrate:author-issue-body:E010-SMOKE-001-real-cli-mint-reports-today
# Acceptance: acc:author-atdd-substrate:E010-SMOKE-001-real-cli-mint-reports-today
# WMBT: wmbt:author-atdd-substrate:E010
# Phase: SMOKE
# Layer: integration
"""E010-SMOKE-001 — the real CLI emits a body dated the day it ran.

The unit guards freeze the clock, which means they can only prove the generator
READS a clock. This one patches nothing: it runs the repo CLI in a real checkout
and compares against the wall clock, so a regression that survives monkeypatching
still fails here.

``--dry-run`` renders and validates the body while writing nothing — no store,
no gh — so the smoke stays hermetic without stubbing anything.
"""
from __future__ import annotations

import datetime
import re

from ._helpers import run_cli

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def test_e010_smoke_001_real_cli_mint_reports_today():
    before = datetime.date.today()
    proc = run_cli(
        "author", "issue",
        "--title", "E010 smoke: the Date row tracks the clock",
        "--slug", "e010-smoke-date-row",
        "--dry-run",
    )
    after = datetime.date.today()

    assert proc.returncode == 0, f"CLI failed: {proc.stderr or proc.stdout}"

    dates = set(_ISO.findall(proc.stdout))
    assert dates, "the emitted body carries no date at all"

    # Tolerate a midnight rollover between the two clock reads.
    acceptable = {before.isoformat(), after.isoformat()}
    stale = sorted(dates - acceptable)
    assert stale == [], (
        f"the real CLI emitted date(s) that are not today: {stale}. "
        f"Expected one of {sorted(acceptable)}."
    )
