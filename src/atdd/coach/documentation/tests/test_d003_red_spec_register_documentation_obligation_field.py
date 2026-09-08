# URN: test:govern-projection-fields:register-documentation-obligation-field:D003-RED-SPEC
# Acceptance: acc:govern-projection-fields:D003-UNIT-001-red-unregistered-documentation-field
# Acceptance: acc:govern-projection-fields:D003-SMOKE-001-real-policy-carries-the-documentation-field
# WMBT: wmbt:govern-projection-fields:D003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED spec for wmbt:govern-projection-fields:D003 — owned by #1826.

The documentation field declares one legal writer and one merge rule, so the field-writer validator admits it.

Every assertion below fails today: the behaviour is unimplemented and #1826 is the
issue that implements it. These live here rather than beside their eventual code
because that code does not exist yet; each moves to its implementation package when
#1826 lands.

They exist now because #1789 authored these acceptances, and an acceptance no test
names is an obligation no gate can ask for —
tester.acceptance-violation.validator-binding-must-be-bidirectional, strict.
"""
from __future__ import annotations

import pytest


def test_unit_001_red_unregistered_documentation_field() -> None:
    """AC-UNIT-001 (RED) — The diff is rejected naming the unowned field

    Given: A projection diff touching the documentation obligation field
    When:  the field-writer validator runs
    """
    pytest.fail(
        "unimplemented: #1826 owns D003-UNIT-001-red-unregistered-documentation-field"
    )


def test_smoke_001_real_policy_carries_the_documentation_field() -> None:
    """AC-SMOKE-001 (SMOKE) — The field resolves to exactly one declared writer and one merge rule

    Given: The committed field-ownership policy in this repository
    When:  the real policy loader resolves the documentation obligation field
    """
    pytest.fail(
        "unimplemented: #1826 owns D003-SMOKE-001-real-policy-carries-the-documentation-field"
    )


