"""Engine-core tests (#1042): Cargo + TrainRunner nominal thread + failures.

Uses injected fake wagons (no real wagon imports) — the engine must be runnable
in isolation. Mirrors the convention's domain-neutral checkout example.
"""
from __future__ import annotations

import pytest

from atdd.journey import (
    Cargo,
    CargoKeyError,
    STATUS_FAILURE,
    STATUS_SUCCESS,
    TrainRunner,
    TrainSpec,
    TrainStep,
)


# --- Cargo ---

def test_cargo_add_get_has():
    c = Cargo()
    assert not c.has_artifact("shop:cart:validated")
    c.add_artifact("shop:cart:validated", {"ok": True})
    assert c.has_artifact("shop:cart:validated")
    assert c.get_artifact("shop:cart:validated") == {"ok": True}


def test_cargo_missing_raises():
    with pytest.raises(CargoKeyError):
        Cargo().get_artifact("nope")


def test_cargo_seeded_from_inputs_and_accumulates():
    c = Cargo({"in:a": 1})
    c.merge({"out:b": 2, "out:c": 3})
    assert set(c.urns()) == {"in:a", "out:b", "out:c"}
    assert c.as_dict() == {"in:a": 1, "out:b": 2, "out:c": 3}


# --- TrainRunner: nominal thread ---

def _resolver(mapping):
    def resolve(name):
        return mapping[name]
    return resolve


def test_nominal_thread_succeeds_and_accumulates_cargo():
    def validate_cart(inputs, timing):
        return {"shop:cart:validated": {"items": 2}}

    def confirm_order(inputs, timing):
        # consumes the upstream artifact from cargo inputs
        assert inputs["shop:cart:validated"] == {"items": 2}
        return {"shop:order:confirmed": {"id": "o-1"}}

    spec = TrainSpec(
        "9001-checkout-standard",
        (
            TrainStep(1, "validate-cart", "shop:cart:validated"),
            TrainStep(2, "confirm-order", "shop:order:confirmed"),
        ),
    )
    runner = TrainRunner(_resolver({
        "validate-cart": validate_cart,
        "confirm-order": confirm_order,
    }))
    result = runner.execute(spec, inputs={})

    assert result.status == STATUS_SUCCESS
    assert result.ok
    assert result.cargo["shop:order:confirmed"] == {"id": "o-1"}
    assert [t["step"] for t in result.trace] == [1, 2]
    assert result.divergence is None


def test_initial_inputs_seed_cargo():
    def step_a(inputs, timing):
        assert inputs["caller:env"] == "preview"
        return {"shop:cart:validated": {}}

    spec = TrainSpec("9002-x", (TrainStep(1, "validate-cart", "shop:cart:validated"),))
    runner = TrainRunner(_resolver({"validate-cart": step_a}))
    result = runner.execute(spec, inputs={"caller:env": "preview"})
    assert result.status == STATUS_SUCCESS


# --- TrainRunner: failures ---

def test_missing_declared_primary_is_failure():
    def wrong(inputs, timing):
        return {"shop:something:else": {}}

    spec = TrainSpec("9003-x", (TrainStep(1, "validate-cart", "shop:cart:validated"),))
    runner = TrainRunner(_resolver({"validate-cart": wrong}))
    result = runner.execute(spec, inputs={})
    assert result.status == STATUS_FAILURE
    assert "not produced" in (result.detail or "")


def test_unresolvable_wagon_is_failure():
    spec = TrainSpec("9004-x", (TrainStep(1, "ghost-wagon", "x:y:z"),))
    runner = TrainRunner(_resolver({}))
    result = runner.execute(spec, inputs={})
    assert result.status == STATUS_FAILURE
    assert "cannot resolve wagon" in (result.detail or "")


def test_non_dict_run_train_return_is_failure():
    spec = TrainSpec("9005-x", (TrainStep(1, "bad", "x:y:z"),))
    runner = TrainRunner(_resolver({"bad": lambda i, t: ["not", "a", "dict"]}))
    result = runner.execute(spec, inputs={})
    assert result.status == STATUS_FAILURE
    assert "must return a dict" in (result.detail or "")
