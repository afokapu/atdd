# URN: test:define-plans:atdd-plan-session:E002-UNIT-002-every-authorable-kind-is-governed
# Acceptance: acc:define-plans:E002-UNIT-002-every-authorable-kind-is-governed
# WMBT: wmbt:define-plans:E002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E002-UNIT-002 — no authorable kind is silently ungoverned (#2013).

`check_unit_spec` returns `(tier, findings)`. For a kind it does not know it
returns `("skip", [])` — indistinguishable, to a caller, from a kind it checked
and found clean. That is the whole defect: silence reads as approval.

`contract` is the kind it hits. #1929 built `SPEC_SCHEMAS` as
`kind -> (schema file, $ref, tier)`, which structurally requires a schema file,
and a contract IS a JSON schema — it has no meta-schema to validate against. So
the kind was omitted rather than modelled, and all three rules
`validate_contract` enforces became invisible before author across 14 registered
contracts.

The fix is not to invent a `contract.schema.json`. It is to let a kind be
governed by its own writer's validator, and to make the absence of any governance
impossible to mistake for a pass.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.plan_unit_schema import (
    AUTHORABLE_KINDS, check_unit_spec,
)

pytestmark = [pytest.mark.planner]


CONTRACT_OK = {
    "identity": "commons:users.record",
    "title": "User record",
    "schema": {"type": "object"},
    "produced_by": ["wagon:manage-users"],
}


def test_no_authorable_kind_returns_the_skip_tier():
    """The coverage invariant. A kind that authors an artifact must be checked by
    something — a schema, or its writer's own rules."""
    ungoverned = sorted(
        kind for kind in AUTHORABLE_KINDS
        if check_unit_spec(kind, {}, stage="ratify")[0] == "skip"
    )
    assert not ungoverned, (
        f"these authorable kinds are checked by nothing and report clean: "
        f"{ungoverned} — a consumer cannot tell that from a pass")


def test_a_malformed_contract_identity_is_reported_before_author():
    _, findings = check_unit_spec(
        "contract", {**CONTRACT_OK, "identity": "Bad Identity"}, stage="ratify")
    assert findings, "validate_contract raises on this; the gate must see it first"
    assert any("identity" in f for f in findings)


def test_a_contract_missing_its_title_is_reported_before_author():
    spec = {k: v for k, v in CONTRACT_OK.items() if k != "title"}
    _, findings = check_unit_spec("contract", spec, stage="ratify")
    assert findings, "validate_contract raises on this; the gate must see it first"
    assert any("title" in f for f in findings)


def test_a_well_formed_contract_is_not_reported():
    """The gate must not become noise — a contract the writer accepts passes."""
    _, findings = check_unit_spec("contract", CONTRACT_OK, stage="ratify")
    assert findings == [], f"a valid contract was reported: {findings}"
