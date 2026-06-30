# URN: test:demo:dirty:UNIT-001-pricing-rounding
# Acceptance: acc:demo:UNIT-001-pricing
# Phase: GREEN
# Layer: unit
"""CONTROL (must NOT be flagged): a plain UNIT test that legitimately self-skips
via @pytest.mark.skipif. It carries NO `# execution_kind: live_smoke` header, so
the live_smoke gate excludes it — proving the detector is false-positive-safe and
does not flag every skippable test, only live_smoke-anchored ones."""
import sys

import pytest


@pytest.mark.skipif(sys.version_info < (3, 10), reason="needs match statement")
def test_price_rounding():
    from app.pricing import round_price

    assert round_price(9.999) == 10.0
