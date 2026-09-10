# acc:verify-validation-receipt:C001-UNIT-002-handedited-verdict-is-rejected
"""RED/guard acceptance for wmbt:verify-validation-receipt:C001.

A receipt hand-edited to assert a pass for a tree nobody validated must not read
as valid. The convenient conflict resolution — pick a side / hand-edit the YAML —
is exactly the false receipt this issue is about (#1566, Decision 1).

Fault-injection discipline: assert the hand-edit landed (recorded hash differs
from the recomputed one) before asserting verify rejects.
"""
from __future__ import annotations

import yaml

from atdd.coach.commands.validation_baseline import (
    compute_source_hash,
    validation_baseline_path,
    verify_validation_baseline,
    write_validation_baseline,
)

_PHASE = "coach"


def test_handedited_receipt_does_not_read_as_pass(tmp_path):
    write_validation_baseline(_PHASE, skipped_api=False, repo_root=tmp_path)
    receipt = validation_baseline_path(tmp_path, _PHASE)

    # Hand-edit: a plausible-looking but incorrect source_hash (one hex nibble
    # flipped from the real one) — the shape a resolver would produce.
    data = yaml.safe_load(receipt.read_text())
    real = data["source_hash"]
    flipped = ("f" if real[0] != "f" else "0") + real[1:]
    data["source_hash"] = flipped
    receipt.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

    # Fault landed?
    assert flipped != compute_source_hash(_PHASE), "fault did not land: edited hash still matches the tree"

    rc = verify_validation_baseline(phase=_PHASE, repo_root=tmp_path)
    assert rc != 0, "a hand-edited receipt read as a valid pass (#1566)"
