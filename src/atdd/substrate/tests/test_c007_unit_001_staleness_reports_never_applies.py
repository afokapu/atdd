# URN: test:admit-substrate:substrate-admission:C007-UNIT-001-staleness-reports-never-applies
# Acceptance: acc:admit-substrate:C007-UNIT-001-staleness-reports-never-applies
# WMBT: wmbt:admit-substrate:C007
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C007-UNIT-001 — staleness is reported, never applied, and an unreadable
registry is COULD_NOT_CHECK rather than "up to date" (#1878).

Core sat three versions behind its hub because nothing pulls after `substrate
add` and nothing reports that it should. Each re-pin happened because a human
noticed.

The load-bearing assertion here is the negative one: a registry that could not be
read must NOT report clean. A staleness check that says "fine" when it could not
look is the same defect as a green badge over a suite that never ran — the
failure this repo hit three separate times in one day (#1818, #1867, #1876).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from atdd.substrate import staleness


@dataclass(frozen=True)
class _Entry:
    id: str
    latest_version: Optional[str] = None


def _installed(**over):
    base = {"id": "demo.ext", "version": "0.1.0"}
    base.update(over)
    return [base]


def test_a_newer_published_version_is_reported_as_stale():
    [r] = staleness.evaluate(_installed(), [_Entry("demo.ext", "0.2.0")])
    assert r.verdict == staleness.PASS
    assert r.is_stale
    assert "0.1.0" in r.detail and "0.2.0" in r.detail


def test_a_matching_version_is_not_stale():
    [r] = staleness.evaluate(_installed(), [_Entry("demo.ext", "0.1.0")])
    assert r.verdict == staleness.PASS
    assert not r.is_stale


def test_an_unreadable_registry_is_could_not_check_not_up_to_date():
    """THE POINT. `None` means the registry could not be read at all."""
    [r] = staleness.evaluate(_installed(), None)
    assert r.verdict == staleness.COULD_NOT_CHECK
    assert not r.is_stale, "an unestablished verdict must not masquerade as a finding"
    assert "not 'up to date'" in r.detail


def test_an_unreadable_registry_blocks_but_mere_staleness_does_not():
    """Being behind is information the operator acts on; not knowing is not."""
    assert staleness.blocks(staleness.evaluate(_installed(), None))
    assert not staleness.blocks(staleness.evaluate(_installed(), [_Entry("demo.ext", "9.9.9")]))


def test_an_empty_registry_is_not_the_same_fact_as_an_unreadable_one():
    """`[]` answered and offers nothing; `None` never answered. Collapsing them is
    how a could-not-check becomes a silent pass."""
    [empty] = staleness.evaluate(_installed(), [])
    [unread] = staleness.evaluate(_installed(), None)
    assert empty.verdict == staleness.NOT_APPLICABLE
    assert unread.verdict == staleness.COULD_NOT_CHECK
    assert empty.verdict != unread.verdict


def test_an_entry_without_a_latest_version_is_could_not_check():
    [r] = staleness.evaluate(_installed(), [_Entry("demo.ext", None)])
    assert r.verdict == staleness.COULD_NOT_CHECK


def test_a_locally_admitted_package_no_registry_publishes_is_not_applicable():
    [r] = staleness.evaluate(_installed(), [_Entry("other.ext", "1.0.0")])
    assert r.verdict == staleness.NOT_APPLICABLE
    assert not r.is_stale


def test_the_summary_never_hides_a_could_not_check_behind_a_clean_line():
    """A mixed run must surface the unknown, not average it away."""
    results = staleness.evaluate(
        [{"id": "a.ext", "version": "1.0.0"}, {"id": "b.ext", "version": "1.0.0"}],
        None,
    )
    text = staleness.summarize(results)
    assert "COULD_NOT_CHECK" in text
    assert "NOT a clean result" in text


def test_the_summary_tells_the_operator_applying_is_theirs():
    results = staleness.evaluate(_installed(), [_Entry("demo.ext", "0.2.0")])
    text = staleness.summarize(results)
    assert "atdd substrate add" in text, "a report that names no remedy is not actionable"
