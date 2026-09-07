# URN: test:govern-lifecycle:live-smoke-attestability:E071-UNIT-002-census-closes-its-open-direction
# Acceptance: acc:govern-lifecycle:E071-UNIT-002-census-closes-its-open-direction
# WMBT: wmbt:govern-lifecycle:E071
# Phase: RED
# Layer: unit
# Assertion: behavioral
# Runtime: python
"""E071-UNIT-002 — the census reports both directions, and repairs neither.

    A row whose acceptance no longer exists in `plan/` is reported as stale; an
    acceptance with no row is reported as missing.

`acc:govern-lifecycle:E027-SMOKE-001` asserts every plan acceptance has a row
but never the converse, so the table accumulates rows for URNs `plan/` has since
dropped. Silently rewriting them would destroy the only record they existed, so
annotation marks and counts them instead.
"""
from __future__ import annotations

from atdd.tester.substrate.attestability import CENSUS_COLUMNS, annotate_census

_CENSUS = (
    "# SMOKE Test Audit\n\n"
    "| acceptance-URN | entry-point-coverage |\n"
    "|---|---|\n"
    "| acc:w:E001-SMOKE-001 | real |\n"
    "| acc:w:E999-SMOKE-999 | real |\n"
)


def test_header_gains_the_derived_columns() -> None:
    new, _, _ = annotate_census(_CENSUS, {"acc:w:E001-SMOKE-001": "can-attest-today"}, {})
    header = [l for l in new.splitlines() if l.startswith("| acceptance-URN")][0]
    for col in CENSUS_COLUMNS:
        assert f"| {col} " in header or header.endswith(f"| {col} |")
    sep = [l for l in new.splitlines() if l.startswith("|") and set(l) <= set("|- ")][0]
    assert sep.count("|") == header.count("|"), "separator must match header arity"


def test_a_row_whose_acceptance_is_gone_is_reported_stale_not_removed() -> None:
    new, stale, _ = annotate_census(_CENSUS, {"acc:w:E001-SMOKE-001": "can-attest-today"}, {})
    assert stale == ["acc:w:E999-SMOKE-999"]
    assert "acc:w:E999-SMOKE-999" in new, "the row must survive; it is the only record"
    assert "stale" in [l for l in new.splitlines() if "E999" in l][0]


def test_an_acceptance_with_no_row_is_reported_missing() -> None:
    _, _, missing = annotate_census(
        _CENSUS,
        {"acc:w:E001-SMOKE-001": "can-attest-today", "acc:w:E777-SMOKE-001": "unresolved"},
        {},
    )
    assert missing == ["acc:w:E777-SMOKE-001"]


def test_annotation_is_idempotent_on_row_count() -> None:
    once, _, _ = annotate_census(_CENSUS, {"acc:w:E001-SMOKE-001": "can-attest-today"}, {})
    assert len([l for l in once.splitlines() if l.startswith("| acc:")]) == 2
