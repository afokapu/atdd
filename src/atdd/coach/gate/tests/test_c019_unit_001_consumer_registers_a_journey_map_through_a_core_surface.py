# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C019-UNIT-001-consumer-registers-a-journey-map-through-a-core-surface
# Acceptance: acc:govern-lifecycle:C019-UNIT-001-consumer-registers-a-journey-map-through-a-core-surface
# WMBT: wmbt:govern-lifecycle:C019
# Phase: RED
# Layer: unit
# Assertion: behavioral
# Purpose: core publishes a surface a consumer hands a journey map to, and names/imports nothing consumer-specific to do it — the seam #1483 left behind acquires the declared other half it never had
"""C019-UNIT-001 — the consumer-facing journey-map registration surface.

Measured on main at ff55607b and re-verified at 7ae53dcb: ``resolve_journey``
takes a journey map HANDED IN, ``TrainExecutor`` is an INJECTED Protocol whose
only in-tree implementation is ``_FakeExecutor`` in
``test_runner_contract.py``, and there are ZERO callers of either outside
``src/atdd/runtime/interlocking/``. Core ships the route-control engine and gives
a consumer nowhere to stand.

WHY THIS SHAPE, AND NOT A CONFIG KEY. ``atdd.state.providers`` (#1364) already
solved this exact problem for the SyncProvider seam: in-process registration
primary, entry-point discovery secondary, zero registrations a valid state, and a
module that never imports a provider. Copying it buys cross-process
discoverability — a gate running in its own process can enumerate entry points,
which it cannot do for an in-memory registration made by somebody else's process.

A new ``.atdd/config.yaml`` key was the rejected alternative. ``interlocking_layout``
is already in this repo pointing the detector at ``src/atdd/runtime/interlocking/*.py``,
and #1598 names it as the shape to avoid: a repo-specific answer standing in for
a general one. The distinction that matters is not "config bad, code good" — it
is that every consumer fills an entry point with ITS OWN value, whereas
``interlocking_layout`` hard-codes atdd's paths so a general check passes in the
one repo it was written in.

ZERO REGISTRATIONS IS NOT A FAULT. It is the shipped default and the state atdd
itself is in, correctly, per #1618 — atdd is the route-control library, not a
Station Master. A surface that errored on an empty registry would make the gate
fail-closed against every repo that never opted in, which is the rubber-stamp
failure ``smoke_obligation.py`` documents at length.

RED state: ``atdd.runtime.interlocking.registry`` does not exist.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]

#: The two journey shapes ``resolve_journey`` already accepts — this surface must
#: not narrow them, or a consumer with a direct-train route cannot register.
_DIRECT = {"start_run": "0007-enforce-extension-conventions"}
_INTERLOCKING = {
    "collaborate": {
        "interlocking_id": "interlocking:collaborate-through-projection",
        "path": "plan/_trains/_interlockings/collaborate-through-projection.yaml",
    }
}


@pytest.fixture(autouse=True)
def _clean_registry():
    """Registrations are process-global; leaking one would bleed into siblings."""
    from atdd.runtime.interlocking.registry import clear_journey_maps

    clear_journey_maps()
    yield
    clear_journey_maps()


def test_zero_registrations_is_a_valid_empty_state():
    """C019-UNIT-001: the shipped default — and atdd's own correct state (#1618)."""
    from atdd.runtime.interlocking.registry import discover_journey_maps

    assert discover_journey_maps() == (), (
        "a repo that installs no consumer is not a fault; an erroring empty "
        "registry would make the gate fail-closed against every repo that never "
        "opted in"
    )


def test_both_journey_shapes_register_and_carry_their_source():
    """C019-UNIT-001: discoverable through one call, and attributable."""
    from atdd.runtime.interlocking.registry import (
        discover_journey_maps,
        register_journey_map,
    )

    register_journey_map(_DIRECT, source="consumer-a")
    register_journey_map(_INTERLOCKING, source="consumer-b")

    found = discover_journey_maps()
    assert len(found) == 2

    by_source = {r.source: r.journey_map for r in found}
    assert by_source["consumer-a"] == _DIRECT
    assert by_source["consumer-b"] == _INTERLOCKING, (
        "the interlocking descriptor shape must survive registration unchanged; "
        "narrowing to direct train_ids alone would drop the shape that actually "
        "routes through InterlockingRunner"
    )

    # Attribution is the point of `source`: a later reader must be able to say
    # WHICH consumer claimed what, not merely that something did. A gate that can
    # only report "a registration exists" cannot name the consumer in its verdict.
    assert set(by_source) == {"consumer-a", "consumer-b"}


def test_core_names_no_consumer_in_its_own_module_graph():
    """C019-UNIT-001: read as SOURCE — an import is a statement, not a value.

    The entry-point group must be the ONLY place a consumer's name can appear. If
    core ever imports a consumer to make this work, the boundary #1483 drew is
    gone and no test asserting behaviour would notice.
    """
    import ast
    import pathlib

    import atdd.runtime.interlocking.registry as mod

    tree = ast.parse(pathlib.Path(mod.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])

    permitted = {
        "atdd", "__future__", "logging", "typing", "dataclasses",
        "importlib", "collections",
    }
    assert imported <= permitted, (
        f"core's registration module imports {sorted(imported - permitted)}; it "
        f"may name nothing consumer-specific — the entry-point group is the only "
        f"place a consumer's name belongs"
    )


def test_a_broken_registration_cannot_blind_the_gate_to_a_working_one():
    """C019-UNIT-001: one bad consumer must not abort discovery.

    Same posture as ``atdd.state.providers.discover_providers``: a factory that
    raises is logged and skipped. Aborting would let a single broken consumer
    turn every OTHER consumer's registration invisible — and an invisible
    registration reads downstream as "no claim", which is the quietest possible
    way to lose the gate.
    """
    from atdd.runtime.interlocking.registry import (
        discover_journey_maps,
        register_journey_map_factory,
    )

    def _explodes():
        raise RuntimeError("this consumer's factory is broken")

    register_journey_map_factory(_explodes, source="consumer-broken")
    register_journey_map_factory(lambda: _DIRECT, source="consumer-ok")

    found = discover_journey_maps()
    sources = {r.source for r in found}
    assert sources == {"consumer-ok"}, (
        f"the working consumer must survive a broken sibling; got {sources}"
    )
