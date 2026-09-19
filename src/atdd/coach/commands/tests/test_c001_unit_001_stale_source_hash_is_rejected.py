# acc:verify-validation-receipt:C001-UNIT-001-stale-source-hash-is-rejected
"""RED/guard acceptance for wmbt:verify-validation-receipt:C001.

verify-on-read must recompute the source hash and REJECT a receipt whose
recorded key does not match the tree it is read against, so a stale or
hand-edited receipt fails instead of being trusted (#1566).

Fault-injection discipline: the test first asserts the injected mismatch
actually landed (the recorded hash really differs from the recomputed one), so
the reject path is genuinely exercised — a verify test that never triggers the
reject would pass green while testing nothing.
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


def test_stale_source_hash_is_rejected(tmp_path):
    # Write an honest receipt for the current tree/version.
    write_validation_baseline(_PHASE, skipped_api=True, repo_root=tmp_path)
    receipt = validation_baseline_path(tmp_path, _PHASE)

    # Inject the fault: overwrite the recorded source_hash with a wrong value.
    data = yaml.safe_load(receipt.read_text())
    forged = "0" * 64
    data["source_hash"] = forged
    receipt.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

    # Assert the fault LANDED — the forged hash must differ from what verify
    # will recompute, otherwise the reject path is never reached.
    assert forged != compute_source_hash(_PHASE), (
        "fault did not land: forged source_hash coincidentally equals the "
        "recomputed hash, so the reject path would not be exercised"
    )

    # verify-on-read must reject (non-zero).
    rc = verify_validation_baseline(phase=_PHASE, repo_root=tmp_path)
    assert rc != 0, (
        "verify-on-read TRUSTED a receipt whose recorded source_hash does not "
        "describe the current tree — a forged pass-receipt read as valid (#1566)"
    )
