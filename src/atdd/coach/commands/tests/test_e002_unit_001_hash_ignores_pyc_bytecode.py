# acc:verify-validation-receipt:E002-UNIT-001-hash-ignores-pyc-bytecode
"""RED acceptance for wmbt:verify-validation-receipt:E002.

compute_source_hash must be computed over toolkit *source* files only — it must
exclude __pycache__ directories and *.pyc bytecode from the installed package —
so the recorded key is reproducible across environments and runs. The issue
observed the hash drift 642f06c1 -> ff1f23a1 with no source change because
rglob("*") sweeps in installed bytecode (#1566).

Fault-injection discipline: assert the injected .pyc actually exists under a
hashed tree before asserting the hash is unchanged.

Fails today because the hash includes __pycache__/*.pyc.
"""
from __future__ import annotations

from pathlib import Path

import atdd
from atdd.coach.commands.validation_baseline import compute_source_hash

_PHASE = "coach"


def test_pyc_bytecode_does_not_change_source_hash():
    pkg_dir = Path(atdd.__file__).resolve().parent
    hashed_subdir = pkg_dir / _PHASE / "validators"
    assert hashed_subdir.is_dir(), f"expected a hashed toolkit dir at {hashed_subdir}"

    baseline = compute_source_hash(_PHASE)

    pycache = hashed_subdir / "__pycache__"
    pycache.mkdir(exist_ok=True)
    injected = pycache / "zz_receipt_1566_probe.cpython-test.pyc"
    injected.write_bytes(b"\x00\x0f\x0a\x0dnot-real-bytecode")
    try:
        # Fault landed?
        assert injected.exists(), "fault did not land: probe .pyc was not created"

        recomputed = compute_source_hash(_PHASE)
        assert recomputed == baseline, (
            "compute_source_hash CHANGED when a __pycache__/*.pyc file appeared "
            "under a hashed toolkit dir — the key is keyed on environment-specific "
            "bytecode and is not reproducible across environments (#1566)"
        )
    finally:
        injected.unlink(missing_ok=True)
