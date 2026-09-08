# URN: test:enforce-conventions-ci:enforce-conventions-ci:E004-UNIT-001-a-new-lint-finding-fails-while-baselined-debt-does-not
# Acceptance: acc:enforce-conventions-ci:E004-UNIT-001-a-new-lint-finding-fails-while-baselined-debt-does-not
# WMBT: wmbt:enforce-conventions-ci:E004
# Phase: RED
# Layer: application
"""E004-UNIT-001 — the ratchet semantics, over a frozen baseline.

Existing debt must not block work; a NEW finding must. Driven over the pure
core so the semantics are pinned without invoking a tool — the tool itself is
the SMOKE acceptance's job.
"""
from __future__ import annotations

from atdd.coder.validators._static_ratchet import (
    Finding,
    finding_identity,
    new_findings,
)


def _f(path, rule, line=1):
    return Finding(path=path, rule=rule, line=line, message=f"{rule} at {path}")


def test_a_finding_absent_from_the_baseline_is_reported():
    baseline = {finding_identity(_f("a.py", "F401"))}

    fresh = new_findings([_f("b.py", "F841")], baseline)

    assert [f.path for f in fresh] == ["b.py"], (
        "a finding the baseline never froze is new debt and must fail the gate"
    )


def test_a_baselined_finding_is_not_reported():
    known = _f("a.py", "F401")

    assert new_findings([known], {finding_identity(known)}) == [], (
        "frozen debt must not block work, or the gate is unusable on day one"
    )


def test_identity_ignores_line_number_drift():
    """A finding must stay identified when unrelated edits move it down the file.

    Keying on the line number would re-report every frozen finding the moment
    anything above it changed — the baseline would decay into noise within days.
    """
    assert finding_identity(_f("a.py", "F401", line=10)) == \
           finding_identity(_f("a.py", "F401", line=99))


def test_a_shrinking_baseline_is_accepted():
    """Debt paid down must not be re-introduced by a stale baseline entry."""
    baseline = {finding_identity(_f("a.py", "F401")),
                finding_identity(_f("gone.py", "F401"))}

    assert new_findings([_f("a.py", "F401")], baseline) == []
