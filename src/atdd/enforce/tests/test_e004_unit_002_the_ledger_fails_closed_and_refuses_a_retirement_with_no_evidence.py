# URN: test:govern-registry:E004-UNIT-002-the-ledger-fails-closed-and-refuses-a-retirement-with-no-evidence
# Acceptance: acc:govern-registry:E004-UNIT-002-the-ledger-fails-closed-and-refuses-a-retirement-with-no-evidence
# WMBT: wmbt:govern-registry:E004
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-registry:E004-UNIT-002-the-ledger-fails-closed-and-refuses-a-retirement-with-no-evidence.

Absence is never the licence.

An absent ledger retires NOTHING. The opposite reading — no file, so nothing is
policed — would silently green the one gate that watches for a lost obligation, which
is the failure this whole mechanism exists to prevent. Compare
``ratchet.load_baseline``, which raises on a missing baseline for the mirror-image
reason: there, absence read as forgiveness would forgive real debt.

An entry with no retiring issue is refused rather than admitted: a retirement asserted
without evidence that it was sanctioned is indistinguishable from one invented to
silence a red gate.

An entry declaring that NOTHING succeeds the rule is admitted and is a real
retirement. A rule genuinely withdrawn must be sayable, and sayable apart from one
whose succession was simply forgotten — that distinction is what #1993's twinless
branch has no way to make today.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.enforce.registry import find_mirror_incoherences
from atdd.enforce.retirements import RetirementError, declared_retirements

from .conftest import write_mirror_node, write_retirement_ledger

_DEAD = "coder.design.token-color"
_WITHDRAWN = "coder.design.orphan-ui"


def test_the_ledger_fails_closed_and_refuses_a_retirement_with_no_evidence(
    tmp_path: Path,
) -> None:
    core_ids: set[str] = set()
    write_mirror_node(tmp_path, rule_id=_DEAD, legacy_rule_id=_DEAD)

    # No ledger at all: nothing is retired, so the drifted mirror is still reported.
    assert declared_retirements(tmp_path) == {}
    assert [
        m.extension_rule_id
        for m in find_mirror_incoherences(
            tmp_path, core_ids, retirements=declared_retirements(tmp_path)
        )
    ] == [_DEAD]

    # An entry with no retiring issue is refused loudly, naming the rule.
    write_retirement_ledger(tmp_path, {_DEAD: {"superseded_by": [_DEAD]}})
    with pytest.raises(RetirementError) as excinfo:
        declared_retirements(tmp_path)
    assert _DEAD in str(excinfo.value)

    # An entry declaring that nothing succeeds the rule IS a retirement.
    write_retirement_ledger(
        tmp_path,
        {
            _DEAD: {"retired_in": "#1518", "superseded_by": [_DEAD]},
            _WITHDRAWN: {"retired_in": "#1518", "superseded_by": []},
        },
    )
    retirements = declared_retirements(tmp_path)
    assert set(retirements) == {_DEAD, _WITHDRAWN}
    assert retirements[_WITHDRAWN].superseded_by == ()
    assert find_mirror_incoherences(tmp_path, core_ids, retirements=retirements) == []
