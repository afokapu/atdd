# URN: test:project-shared-state:compute-projection-digest:E003-UNIT-002-golden-files-pin-canonical-bytes
# Acceptance: acc:project-shared-state:E003-UNIT-002-golden-files-pin-canonical-bytes
# WMBT: wmbt:project-shared-state:E003
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: Freshly projected bytes and digest match the committed golden fixture exactly, and mutating one golden byte fails with a diff naming the offending file. Refs #1433.
"""Golden files pin the canonical bytes (E003-UNIT-002).

wagon: project-shared-state | feature: compute-projection-digest | phase: GREEN
WMBT: wmbt:project-shared-state:E003

A determinism claim nobody re-checks decays. The golden fixture is the tripwire: a
serializer change that quietly reorders a key, drops a null, or rewraps a line moves
these bytes, and this test names the file it moved. Refs #1433 / #1400.
"""
from __future__ import annotations

from atdd.state.projection import compare_projections, project, projection_digest

from ._helpers import GOLDEN_DIGEST_FILE, GOLDEN_DIR, GOLDEN_UIDS, golden_store, memory_store


def test_e003_unit_002_golden_files_pin_canonical_bytes(tmp_path) -> None:
    """Fresh bytes and digest equal the golden fixture; a mutated golden byte is reported."""
    fresh = tmp_path / "fresh"
    with memory_store() as (conn, _):
        project(golden_store(conn), fresh)

    # Bytes match the golden fixture exactly, file for file.
    assert compare_projections(GOLDEN_DIR, fresh) == []
    for uid in GOLDEN_UIDS:
        assert (fresh / f"{uid}.yaml").read_bytes() == (GOLDEN_DIR / f"{uid}.yaml").read_bytes()

    # ...and so does the recorded digest.
    assert projection_digest(fresh) == GOLDEN_DIGEST_FILE.read_text(encoding="utf-8").strip()

    # Mutating one golden byte makes the comparison fail with a diff naming the
    # offending file. (The mutation is made on a copy — the committed fixture is
    # never touched.)
    tampered = tmp_path / "tampered"
    tampered.mkdir()
    for uid in GOLDEN_UIDS:
        (tampered / f"{uid}.yaml").write_bytes((GOLDEN_DIR / f"{uid}.yaml").read_bytes())
    offender = f"{GOLDEN_UIDS[0]}.yaml"
    (tampered / offender).write_bytes(
        (tampered / offender).read_bytes().replace(b"phase: PLANNED", b"phase: GREEN")
    )

    mismatches = compare_projections(GOLDEN_DIR, tampered)
    assert [m.filename for m in mismatches] == [offender]
    assert "-phase: PLANNED" in mismatches[0].diff
    assert "+phase: GREEN" in mismatches[0].diff
    assert projection_digest(tampered) != projection_digest(GOLDEN_DIR)
