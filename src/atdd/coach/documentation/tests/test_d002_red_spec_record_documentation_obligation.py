# URN: test:define-plans:record-documentation-obligation:D002-RED-SPEC
# Acceptance: acc:define-plans:D002-UNIT-001-red-ratify-records-declaration
# Acceptance: acc:define-plans:D002-UNIT-002-absent-declaration-is-advisory
# Acceptance: acc:define-plans:D002-SMOKE-001-real-ratify-persists-the-declaration
# WMBT: wmbt:define-plans:D002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED spec for wmbt:define-plans:D002 — owned by #1825.

The declaration is recorded at RATIFY as first-class work-item state, not parsed out of a markdown heading.

Every assertion below fails today: the behaviour is unimplemented and #1825 is the
issue that implements it. These live here rather than beside their eventual code
because that code does not exist yet; each moves to its implementation package when
#1825 lands.

They exist now because #1789 authored these acceptances, and an acceptance no test
names is an obligation no gate can ask for —
tester.acceptance-violation.validator-binding-must-be-bidirectional, strict.
"""
from __future__ import annotations

import pytest


def test_unit_001_red_ratify_records_declaration() -> None:
    """AC-UNIT-001 (RED) — The declaration is persisted on the work item as typed state

    Given: A session at Ratify carrying a documentation impact of change with one artifact
    When:  the decomposition is ratified
    """
    pytest.fail(
        "unimplemented: #1825 owns D002-UNIT-001-red-ratify-records-declaration"
    )


def test_unit_002_absent_declaration_is_advisory() -> None:
    """AC-UNIT-002 (GREEN) — The omission is reported and does not block

    Given: A ratified plan carrying no documentation declaration
    When:  the advisory disposition is in force
    """
    pytest.fail(
        "unimplemented: #1825 owns D002-UNIT-002-absent-declaration-is-advisory"
    )


def test_smoke_001_real_ratify_persists_the_declaration() -> None:
    """AC-SMOKE-001 (SMOKE) — The declaration is readable from the real State Store afterwards

    Given: A real plan session at Ratify carrying a documentation declaration
    When:  the session is ratified through the real `atdd plan ratify`
    """
    pytest.fail(
        "unimplemented: #1825 owns D002-SMOKE-001-real-ratify-persists-the-declaration"
    )


