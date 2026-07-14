# URN: test:govern-lifecycle:ship-package-data-and-consumer-ci:C008-UNIT-004-rule-node-carries-a-gating-disposition
# Acceptance: acc:govern-lifecycle:C008-UNIT-004-rule-node-carries-a-gating-disposition
# WMBT: wmbt:govern-lifecycle:C008
# Phase: GREEN
# Layer: backend.domain
# Assertion: structural
"""C008-UNIT-004 — the wheel-completeness rule can actually fail a build.

`coach.wheel-completeness.fixture-missing-from-wheel` has sat at
``disposition: advisory`` since 3.7.1, with a source comment promising a flip to
strict "in 3.8.0". The toolkit is now on 4.x. Under `advisory` the disposition
gate logs a warning and PASSES (``disposition_gate``: *"advisory — violations log
a warning and pass"*), so even a gate that ran and saw the missing files could not
have turned a build red.

A validator whose violations never fail anything is documentation, not enforcement.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.rule_binding import bind_rule

# `platform` marks this a TOOLKIT-SELF test: it needs the toolkit checkout (and/or a
# wheel built from it), which a consumer repo does not have. `atdd validate <phase>`
# adds `-m "not platform"` outside the source repo (E025), so this is deselected there
# and runs here. Without the marker these ship in the wheel and ERROR in every
# consumer's sweep — the #954 self-test-leak pathology, which this issue must not add to.
pytestmark = [pytest.mark.coach, pytest.mark.platform]

_RULE_ID = "coach.wheel-completeness.fixture-missing-from-wheel"

# `strict` fails CI on any violation; `suppress-and-clean` fails on any violation
# that is not explicitly, visibly suppressed. `advisory` fails nothing.
_GATING_DISPOSITIONS = frozenset({"strict", "suppress-and-clean"})


def test_c008_unit_004_rule_node_carries_a_gating_disposition():
    rule = bind_rule(_RULE_ID)

    assert rule.disposition in _GATING_DISPOSITIONS, (
        f"{_RULE_ID} carries disposition {rule.disposition!r}, which fails nothing. "
        f"The rule exists to turn a packaging regression red; under 'advisory' the "
        f"disposition gate logs a warning and passes. Expected one of "
        f"{sorted(_GATING_DISPOSITIONS)}."
    )


def test_c008_unit_004_binding_survives_the_disposition_flip():
    """Anti-orphan control: the validator's bind_rule id still resolves."""
    rule = bind_rule(_RULE_ID)

    assert rule.rule_id == _RULE_ID, (
        "the validator's bind_rule() id no longer resolves against the convention "
        "node — flipping the disposition orphaned the binding"
    )
    assert rule.severity is not None, (
        "the bound rule carries no severity, so its Violations cannot be graded"
    )
