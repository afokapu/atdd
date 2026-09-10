# URN: component:coach:PreSmokeGateScope:backend:tests
# Runtime: python
# Purpose: the pre-smoke merge gate reports what it examined, not only its verdict (#1876).
"""A strict gate must say what it LOOKED AT (#1876).

#1871 merged past `coach.pr.merge-blocks-on-pre-smoke-close` with its issue at
`atdd:INIT`, while #1833 and #1839 were blocked the same day for the identical
condition. Five hypotheses were tested and all five invalidated — E056 scoping,
pagination, a link race, a missing `pull-requests: read` scope, a missing
`GH_TOKEN`. None held.

Diagnosis stalled on a measurement problem rather than a reasoning one: every
diagnostic this gate emits is `logging.INFO`, and CI runs `pytest -v` with no
`--log-cli-level`, so a run that scanned 22 open PRs and a run that scanned zero
produce byte-identical output. Verified: zero INFO lines appear anywhere in
#1871's job log.

These tests pin the observability, not the verdict — the verdict is unchanged
until the cause is known.
"""
from __future__ import annotations

import warnings

import pytest

from atdd.coach.validators import test_pr_merge_blocks_pre_smoke_close as gate


def test_a_zero_pr_scan_warns_that_nothing_was_examined(monkeypatch):
    """The vacuous case must be visible on a PASSING run.

    Silence here is what made #1871 indistinguishable from a real green.
    """
    monkeypatch.setattr(gate, "_observed_open_prs", lambda *_a, **_k: [])
    monkeypatch.setattr(gate, "scan_open_prs_for_pre_smoke_close", lambda *_a, **_k: [])
    monkeypatch.setattr(gate, "_current_pr_number", lambda *_a, **_k: None)
    with pytest.warns(UserWarning, match="scanned ZERO open PRs"):
        gate.test_no_open_pr_closes_an_issue_in_pre_smoke_phase()


def test_a_normal_scan_does_not_warn(monkeypatch):
    """Low noise, or the signal is worthless: only the vacuous case warns."""
    monkeypatch.setattr(gate, "_observed_open_prs", lambda *_a, **_k: [{"number": 1}, {"number": 2}])
    monkeypatch.setattr(gate, "scan_open_prs_for_pre_smoke_close", lambda *_a, **_k: [])
    monkeypatch.setattr(gate, "_current_pr_number", lambda *_a, **_k: None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        gate.test_no_open_pr_closes_an_issue_in_pre_smoke_phase()
    zero_warnings = [w for w in caught if "scanned ZERO open PRs" in str(w.message)]
    assert zero_warnings == []


def test_the_warning_does_not_change_the_verdict(monkeypatch):
    """Observability only. A zero-PR scan still passes, exactly as before —
    changing that without knowing the cause would trade a silent gate for a
    broken one."""
    monkeypatch.setattr(gate, "_observed_open_prs", lambda *_a, **_k: [])
    monkeypatch.setattr(gate, "scan_open_prs_for_pre_smoke_close", lambda *_a, **_k: [])
    monkeypatch.setattr(gate, "_current_pr_number", lambda *_a, **_k: None)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gate.test_no_open_pr_closes_an_issue_in_pre_smoke_phase()  # must not raise


def test_observed_open_prs_drops_entries_without_a_number(monkeypatch):
    """The helper answers 'what did you look at', so it must count only PRs it
    could actually identify."""
    class _Mgr:
        def __init__(self, *a, **k): pass
        def fetch_open_prs(self):
            return [{"number": 7}, {"title": "no number"}, {"number": 9}]
    monkeypatch.setattr(gate, "PRManager", _Mgr)
    assert [p["number"] for p in gate._observed_open_prs()] == [7, 9]
