# URN: test:author-atdd-substrate:project-documentation-obligation:E011-RED-SPEC
# Acceptance: acc:author-atdd-substrate:E011-UNIT-001-red-body-is-never-read-back
# Acceptance: acc:author-atdd-substrate:E011-SMOKE-001-real-revise-projects-the-declaration-one-way
# WMBT: wmbt:author-atdd-substrate:E011
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED spec for wmbt:author-atdd-substrate:E011 — owned by #1827.

The stored declaration is rendered into the issue body one way; the body row is never read back.

Every assertion below fails today: the behaviour is unimplemented and #1827 is the
issue that implements it. These live here rather than beside their eventual code
because that code does not exist yet; each moves to its implementation package when
#1827 lands.

They exist now because #1789 authored these acceptances, and an acceptance no test
names is an obligation no gate can ask for —
tester.acceptance-violation.validator-binding-must-be-bidirectional, strict.
"""
from __future__ import annotations

import pytest


def test_unit_001_red_body_is_never_read_back() -> None:
    """AC-UNIT-001 (RED) — The store value is used

    Given: An issue body whose documentation row has been hand-edited to disagree with the store
    When:  the obligation is resolved for a gate decision
    """
    pytest.fail(
        "unimplemented: #1827 owns E011-UNIT-001-red-body-is-never-read-back"
    )


def test_smoke_001_real_revise_projects_the_declaration_one_way() -> None:
    """AC-SMOKE-001 (SMOKE) — The rendered body carries the stored declaration

    Given: A real store-registered issue whose documentation declaration has changed
    When:  the real `atdd author issue --revise` runs
    """
    pytest.fail(
        "unimplemented: #1827 owns E011-SMOKE-001-real-revise-projects-the-declaration-one-way"
    )


