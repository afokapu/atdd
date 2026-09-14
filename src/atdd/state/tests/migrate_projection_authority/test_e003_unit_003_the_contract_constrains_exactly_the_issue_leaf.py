# URN: test:migrate-projection-authority:migrate-store-projection:E003-UNIT-003-the-contract-constrains-exactly-the-issue-leaf
# Acceptance: acc:migrate-projection-authority:E003-UNIT-003-the-contract-constrains-exactly-the-issue-leaf
# WMBT: wmbt:migrate-projection-authority:E003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the contract types the github.issue leaf as a digit string and constrains NOTHING else — narrowing external_refs would refuse writes provider_seam.apply_updates is designed to make and break merge_driver._bot_only's disjoint-provider union. Refs #2025.
"""The contract constrains exactly the issue leaf (E003-UNIT-003).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:E003

Two failure modes sit on opposite sides of one decision, and a contract that fixes either
one alone causes the other.

TOO LOOSE. `FIELD_TYPES` types `external_refs` as `dict` and reaches no deeper, so
`'1975'`, `1975`, `{"number": 1975}` and `["1975"]` are all admitted. The store column is
TEXT, so the value projects as a quoted string — but `'1975'` and `1975` serialize to
DIFFERENT BYTES, so a hand-edit that drops the quotes re-projects differently and breaks
`project(hydrate(p)) == p` with no schema violation to explain it.

TOO TIGHT. `provider_seam.validate_update` constrains the uid, the bot namespace,
authoritativeness and provider IDENTITY — it enumerates neither provider nor ref kind. So
`github/pr`, `jira/ticket` and `linear/issue` are all legal writes, and
`merge_driver._bot_only` unions disjoint providers by design. Closing the field to
`github.issue` would refuse writes the bot is built to make and produce merge results the
schema then rejects.

So: type the leaf, close nothing else.

RED: every malformed shape is admitted today.
"""
from __future__ import annotations

import pytest

from atdd.state.projection import ProjectionSchemaError, validate_document

_UID = "wi_01HF7YAT00M78607F000000001"


def _document(external_refs) -> dict:
    return {
        "uid": _UID, "phase": "PLANNED", "state": "ACTIVE",
        "owner_actor": "atdd:unattributed", "external_refs": external_refs,
    }


@pytest.mark.parametrize(
    "malformed, why",
    [
        ({"github": {"issue": 1975}}, "an unquoted integer — the hand-edit that breaks byte-stability"),
        ({"github": {"issue": {"number": 1975}}}, "a mapping where a scalar belongs"),
        ({"github": {"issue": ["1975"]}}, "a list where a scalar belongs"),
        ({"github": {"issue": "not-a-number"}}, "a non-digit string"),
    ],
)
def test_a_malformed_issue_leaf_is_refused(malformed, why) -> None:
    """The contract reaches INSIDE external_refs to type the issue leaf."""
    with pytest.raises(ProjectionSchemaError) as caught:
        validate_document(_document(malformed))
    assert "external_refs" in str(caught.value), (
        f"the refusal must name the offending field; {why} was admitted or refused "
        "without saying why"
    )


@pytest.mark.parametrize(
    "legal, writer",
    [
        ({"github": {"issue": "1975"}}, "the projector, from the refs table"),
        ({"github": {"pr": "2028"}}, "apply_updates — a second ref kind under one provider"),
        ({"jira": {"ticket": "ATDD-17"}}, "apply_updates — a different provider"),
        ({"linear": {"issue": "ENG-42"}}, "apply_updates — another provider"),
        ({"github": {"issue": "1975", "pr": "2028"}, "jira": {"ticket": "ATDD-17"}},
         "the realistic mixed case"),
    ],
)
def test_every_legal_bot_write_still_validates(legal, writer) -> None:
    """external_refs stays OPEN: narrowing it would refuse writes the bot is designed to make."""
    validate_document(_document(legal))  # must not raise
