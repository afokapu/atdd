# URN: test:demo:dirty:SMOKE-001-checkout-substitutes-collaborators
# Phase: SMOKE
# Layer: integration
"""RED fixture: three collaborator substitutions in a SMOKE test. The detector
emits THREE raw violations; the downstream consumer's suppress-and-clean
disposition turns that into TWO unsuppressed -> FAIL.

  - monkeypatch.setattr over a collaborator                 -> unsuppressed
  - obj.method = local function assigned over an attribute  -> unsuppressed
  - monkeypatch.setattr, MARKED with a suppress marker      -> suppressed
"""


def _fake_charge(amount):
    return {"status": "ok"}


def test_checkout_smoke(monkeypatch):
    from app.checkout import CheckoutService

    service = CheckoutService()

    # 1) collaborator stubbing — unit test wearing a SMOKE label.
    monkeypatch.setattr(service, "payment_gateway", object())

    # 2) local function assigned over a collaborator attribute.
    service.charge = _fake_charge

    # 3) another substitution, but suppressed inline (consumer absorbs this one).
    monkeypatch.setattr(service, "inventory", object())  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2099-01-01

    assert service.checkout("cart-1")
