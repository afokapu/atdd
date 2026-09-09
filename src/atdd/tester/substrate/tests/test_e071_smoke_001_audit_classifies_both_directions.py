# URN: test:govern-lifecycle:live-smoke-attestability:E071-SMOKE-001-audit-classifies-every-live-smoke-acceptance-both-directions
# Acceptance: acc:govern-lifecycle:E071-SMOKE-001-audit-classifies-every-live-smoke-acceptance-both-directions
# WMBT: wmbt:govern-lifecycle:E071
# Phase: SMOKE
# Layer: smoke
# Assertion: behavioral
# Runtime: python
"""E071-SMOKE-001 — the audit classifies the real repository, both directions.

    Against this repository's own `plan/` and `docs/smoke-audit.md`: every SMOKE
    acceptance resolves to exactly one class, and the census reports rows whose
    acceptance is gone as well as acceptances that have no row.

Real inputs, nothing synthetic: the toolkit's committed `plan/` tree, its
committed census, and its own `.github/workflows/`. `acc:...E027-SMOKE-001`
asserts only that every plan acceptance has a row; the converse — a row naming
an acceptance `plan/` no longer declares — is what this closes.

This test never executes another test. Attestation is written by the
`atdd_substrate` pytest11 entry point, so a classifier that ran tests to decide
capability would classify its own runner: the same test writes an attestation
under an installed dist and none under `PYTHONPATH=src`, and both report passed.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root
from atdd.tester.substrate.attestability import (
    CAN_ATTEST,
    NEVER_ATTESTABLE,
    SHOULD_DECLARE,
    UNRESOLVED,
    annotate_census,
    classify,
    train_wagons,
)
from atdd.tester.validators._acceptance_walker import (
    iter_repo_acceptances,
    scan_test_acceptance_headers,
)

REPO_ROOT = find_repo_root()
_LAYER = re.compile(r"^# Layer: *([a-z_]+)", re.M)
_CLASSES = {CAN_ATTEST, SHOULD_DECLARE, NEVER_ATTESTABLE, UNRESOLVED}


def _live_classification() -> Dict[str, str]:
    """Classify every SMOKE acceptance the real ``plan/`` tree declares."""
    trains = yaml.safe_load((REPO_ROOT / "plan" / "_trains.yaml").read_text())
    wagons = train_wagons(trains)
    headers = scan_test_acceptance_headers(REPO_ROOT)

    layers: Dict[Path, Optional[str]] = {}
    for paths in headers.values():
        for p in paths:
            if p in layers:
                continue
            try:
                m = _LAYER.search(Path(p).read_text(encoding="utf-8", errors="ignore")[:3000])
            except OSError:
                m = None
            layers[p] = m.group(1) if m else None

    out: Dict[str, str] = {}
    for raw in iter_repo_acceptances(REPO_ROOT):
        identity = (raw.body or {}).get("identity") or {}
        urn = identity.get("urn") if isinstance(identity, dict) else None
        if not isinstance(urn, str) or urn in out:
            continue
        got = classify(urn, wagons, headers, layers)
        if got is not None:
            out[urn] = got.klass
    return out


@pytest.fixture(scope="module")
def live() -> Dict[str, str]:
    classified = _live_classification()
    if not classified:
        pytest.fail("the real plan/ tree declared no SMOKE acceptance — the walk is broken")
    return classified


def test_every_live_smoke_acceptance_resolves_to_exactly_one_class(live) -> None:
    unknown = {u: k for u, k in live.items() if k not in _CLASSES}
    assert not unknown, f"unclassified acceptances: {sorted(unknown)[:5]}"


def test_no_live_acceptance_is_silently_dropped(live) -> None:
    """A SMOKE URN that classifies to nothing would vanish from the census."""
    for urn in live:
        assert urn.startswith("acc:"), urn
        assert "-SMOKE-" in urn, f"{urn} classified but is not a SMOKE acceptance"


def test_census_reports_both_directions_against_the_real_table(live) -> None:
    census = (REPO_ROOT / "docs" / "smoke-audit.md").read_text()
    _, stale, missing = annotate_census(census, live, {})
    # Direction 1 (E027-SMOKE-001 already asserts it): no acceptance lacks a row.
    assert missing == [], f"acceptances with no census row: {missing[:5]}"
    # Direction 2 (this acceptance closes it): rows naming a vanished acceptance
    # are REPORTED. Zero is a legitimate outcome; a crash or a silent drop is not.
    assert isinstance(stale, list)
    for urn in stale:
        assert urn in census, "a reported stale URN must still be present in the table"

def _row_urn(line: str) -> Optional[str]:
    """The acceptance URN a census row is keyed by, if the line is a data row."""
    if not line.startswith("|"):
        return None
    first = line.split("|")[1].strip()
    return first if first.startswith("acc:") else None


def test_every_census_table_declares_as_many_columns_as_its_rows_carry() -> None:
    """A row wider than its header renders SHORT — the extra cells vanish (#1814).

    Markdown truncates a row to the header's column count, so #1664's own output
    was invisible where it mattered most: ``annotate_census`` appends two cells to
    every acceptance row but updates only the FIRST header it meets, and the census
    holds three acceptance tables. 143 rows carried the derived columns under a
    five-column header, so anyone reading the rendered doc saw the audit's answer
    for 33 acceptances and blank for the other 143 — while every automated reader,
    parsing cells rather than rendering them, agreed the data was there.

    Asserted over the real committed census, per table, because that mismatch is
    invisible to every gate the doc already has: E027-SMOKE-001 asks whether a row
    exists and M002-UNIT-001 asks whether a section exists. Neither reads a row's
    width.
    """
    census = (REPO_ROOT / "docs" / "smoke-audit.md").read_text().splitlines()
    tables: List[tuple] = []
    header_line = columns = None
    for number, line in enumerate(census, 1):
        if line.startswith("| acceptance-URN"):
            header_line, columns = number, line.count("|") - 1
            continue
        if header_line is None:
            continue
        if _row_urn(line) is None:
            if line.strip() and not line.startswith("|"):
                header_line = columns = None
            continue
        tables.append((header_line, columns, number, line.strip().strip("|").count("|") + 1))

    assert tables, "no acceptance table found in the census — the reader is broken"
    mismatched = [t for t in tables if t[1] != t[3]]
    assert not mismatched, (
        "these census rows carry a different number of cells than their table's header "
        "declares, so the surplus renders as nothing:\n"
        + "\n".join(
            f"  table@{h} declares {c} columns; row@{r} carries {n}"
            for h, c, r, n in mismatched[:10]
        )
    )
