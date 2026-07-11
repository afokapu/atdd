# URN: test:project-shared-state:project-store:C001-UNIT-002-orders-unordered-collections
# Acceptance: acc:project-shared-state:C001-UNIT-002-orders-unordered-collections
# WMBT: wmbt:project-shared-state:C001
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: Sets and dicts reaching the serializer are emitted in a total, content-derived order — identical under two PYTHONHASHSEED values, and not the insertion or hash order. Refs #1433.
"""Unordered collections get a content-derived order (C001-UNIT-002).

wagon: project-shared-state | feature: project-store | phase: GREEN
WMBT: wmbt:project-shared-state:C001

CPython's iteration order for a set of strings is a function of PYTHONHASHSEED, so
a serializer that trusted it would emit different bytes on every process. The proof
has to be a real second process: this test re-runs the serializer under two seeds
and compares the bytes. Refs #1433 / #1400.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from atdd.state.projection import canonical_bytes

_SRC = Path(__file__).resolve().parents[4]

#: The wmbts arrive as an unordered SET and the external_refs as a DICT — neither
#: carries an order the serializer may trust.
_SERIALIZE = """
import sys
from atdd.state.projection import canonical_bytes

document = {
    "uid": "wi_01HF7YAT00M78607F000000009",
    "slug": "unordered",
    "phase": "INIT",
    "state": "ACTIVE",
    "owner_actor": "dev-a",
    "wmbts": {"wmbt:w:E003", "wmbt:w:C001", "wmbt:w:E001", "wmbt:w:Y002", "wmbt:w:A001"},
    "external_refs": {"bot:zeta": {"z": "1"}, "bot:alpha": {"a": "2"}, "bot:mid": {"m": "3"}},
}
sys.stdout.buffer.write(canonical_bytes(document))
"""


def _serialize_under(seed: str) -> bytes:
    env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(_SRC)}
    result = subprocess.run(
        [sys.executable, "-c", _SERIALIZE],
        env=env, capture_output=True, timeout=120, check=True,
    )
    return result.stdout


def test_c001_unit_002_orders_unordered_collections(tmp_path) -> None:
    """Two PYTHONHASHSEEDs yield the same bytes, in content order — not insertion order."""
    first = _serialize_under("0")
    second = _serialize_under("12345")

    # The emitted sequence order is identical under both hash seeds.
    assert first == second, "projection bytes moved with PYTHONHASHSEED"

    # The order is derived from element content, not from insertion or hash order:
    # the set was written E003-first, and the mapping zeta-first, yet both come out
    # sorted by content.
    text = first.decode("utf-8")
    wmbts = [line.strip("- ").strip() for line in text.splitlines() if line.startswith("- ")]
    assert wmbts == sorted(wmbts)
    assert wmbts[0] == "wmbt:w:A001"

    refs = [line.strip().rstrip(":") for line in text.splitlines() if line.startswith("  bot:")]
    assert refs == sorted(refs)
    assert refs[0] == "bot:alpha"

    # And the in-process serializer agrees with both subprocesses.
    assert canonical_bytes(
        {
            "uid": "wi_01HF7YAT00M78607F000000009",
            "slug": "unordered",
            "phase": "INIT",
            "state": "ACTIVE",
            "owner_actor": "dev-a",
            "wmbts": {"wmbt:w:E003", "wmbt:w:C001", "wmbt:w:E001", "wmbt:w:Y002", "wmbt:w:A001"},
            "external_refs": {
                "bot:zeta": {"z": "1"}, "bot:alpha": {"a": "2"}, "bot:mid": {"m": "3"},
            },
        }
    ) == first
