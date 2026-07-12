# URN: test:demo:clean:SMOKE-001-payments-against-real-gateway
# Acceptance: acc:demo:SMOKE-001-payments-live
# execution_kind: live_smoke
# Phase: SMOKE
# Layer: integration
"""GREEN fixture: a live_smoke-anchored test with NO self-skip mechanism. It
runs-or-fails against the real gateway -> RAW = [] -> disposition PASS."""
import pytest

pytestmark = [pytest.mark.platform]


def test_charges_real_gateway():
    from app.payments import Gateway

    gateway = Gateway()  # real boundary — no skip guard, must run or fail
    receipt = gateway.charge("acct-1", 1000)
    assert receipt.settled
