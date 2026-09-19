# URN: test:govern-registry:D001-SMOKE-001-real-registry-roots-at-core-only
# Acceptance: acc:govern-registry:D001-SMOKE-001-real-registry-roots-at-core-only
# WMBT: wmbt:govern-registry:D001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:govern-registry:D001-SMOKE-001-real-registry-roots-at-core-only.

Over the toolkit's real substrate the core rule registry admits zero files from the
extension tree, so the core-only ROOTING holds live.

Re-premised by #2002. This test originally also asserted that every extension rule_id
was already a core rule_id -- that admitting the extensions "would add no new rule".
That premise was true when D001 was written (2026-07-10: 50 extension ids, all mirrors
of 373 core ids) and was falsified on 2026-07-18 by commit 47c4d414, "stop declaring
TypeScript and frontend rule_ids in core", which removed 18 TypeScript and frontend
rule_ids from core while the extension nodes mirroring them remained. With 17
train-interlocking nodes added since, the real extension-only set is now 35.

That half is superseded by acc:govern-registry:D002-SMOKE-001, which measures the 35
directly. What survives here is the ROOTING claim -- and it is no longer incidental:
D002 pins ``core_convention_files`` to the core root, so this test is now the live
regression guard for that pin.
"""
from __future__ import annotations

from atdd.enforce.registry import core_convention_files


def test_real_registry_roots_at_core_only() -> None:
    admitted = core_convention_files()
    assert admitted, "core registry unexpectedly empty"

    # No file admitted into the CORE registry lives under the extension tree.
    intruders = [p for p in admitted if ".atdd/extensions" in str(p)]
    assert not intruders, (
        f"{len(intruders)} extension file(s) admitted into the core registry: "
        f"{[str(p) for p in intruders[:3]]}"
    )
