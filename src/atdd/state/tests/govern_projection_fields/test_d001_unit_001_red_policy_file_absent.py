# URN: test:govern-projection-fields:define-field-ownership:D001-UNIT-001-red-policy-file-absent
# Acceptance: acc:govern-projection-fields:D001-UNIT-001-red-policy-file-absent
# WMBT: wmbt:govern-projection-fields:D001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: loading the field-ownership policy from a checkout that commits none raises PolicyNotFound naming the expected path, and never returns an implicit empty ownership table — which would admit every writer for every field, silently Refs #1400.
"""No policy is an error, never an empty table (D001-UNIT-001).

wagon: govern-projection-fields | feature: define-field-ownership | phase: RED
WMBT: wmbt:govern-projection-fields:D001

The tempting implementation is a loader that shrugs: no file, no entries, an empty ownership
table. It would be the worst possible failure, because an empty table *passes everything*.
Every wrong-writer check would come back green, on every diff, forever — and the report would
say "every projection field was written by its owner", which is a sentence that is true only
in the sense that nothing has an owner.

So: a missing policy raises, and the exception names the path it looked at.
"""
from __future__ import annotations

import pytest

from atdd.state import ownership
from atdd.state.ownership import POLICY_RELATIVE, PolicyNotFound


def test_d001_unit_001_red_policy_file_absent(tmp_path) -> None:
    """The loader raises PolicyNotFound naming the path, and returns no table at all."""
    with pytest.raises(PolicyNotFound) as raised:
        ownership.load_policy(tmp_path)

    error = raised.value
    assert error.path == tmp_path / POLICY_RELATIVE
    assert str(POLICY_RELATIVE) in str(error)
    assert "field-ownership.yaml" in str(error)

    # It is a refusal, not a default: no ownership table came back, empty or otherwise.
    with pytest.raises(PolicyNotFound):
        ownership.load_document(tmp_path)

    # The distinction that makes it load-bearing: an EMPTY table would pass any diff, because
    # a field nobody owns is a field nobody may be accused of writing.
    empty = ownership.FieldOwnershipPolicy.from_document({"fields": []})
    permissive = ownership.check_coverage({"fields": []})
    assert not permissive.ok, "an empty table is not a policy; the coverage check says so"
    assert sorted(permissive.uncovered) == sorted(ownership.schema_fields())
    assert not empty.fields
