"""
Asserts the rule ``planner.wmbt.must-have-smoke-acceptance`` is registered in
its canonical convention home — its single-node file
``src/atdd/planner/conventions/nodes/planner.wmbt.must-have-smoke-acceptance.convention.yaml``
(#1225 made the rule registry read ``nodes/`` single-node files; the rule's
authoritative representation moved off the monolith ``wmbt.convention.yaml``
``rules:`` block).

This validator-test is intentionally unanchored (no ``# Acceptance:`` URN
header). #921 is a small test-repair tracking issue with no planned WMBT in
``plan/govern_lifecycle/``, so a bidirectional acceptance binding would be
artificial. The pattern mirrors ``test_hierarchy_coverage.py`` (also
unanchored).

Background (#921 — split from #919 Section A discussion): the prior
template-reader test asserted the rule id string appeared in ``CONDUCTOR.md``.
That was the wrong substrate check — duplicating convention rule IDs into the
agent-facing template re-introduced the dual-source-of-truth pattern the Coach
Decomposition (#887) was actively removing. The rule lives in the convention
substrate; this test asserts that fact via the rule registry (which resolves
the single-node file) — NOT by reading the agent template.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from atdd.coach.utils.rule_binding import RuleNotInRegistryError, bind_rule

RULE_ID = "planner.wmbt.must-have-smoke-acceptance"
_NODE_FILENAME = f"{RULE_ID}.convention.yaml"


def test_wmbt_convention_registers_must_have_smoke_acceptance_rule() -> None:
    """The rule is registered in the convention substrate (its canonical
    single-node ``nodes/`` home), NOT duplicated into CONDUCTOR.md."""
    # The rule registry (build_registry / bind_rule) reads nodes/ single-node
    # files since #1225 — resolution here is the registration check.
    try:
        meta = bind_rule(RULE_ID)
    except RuleNotInRegistryError as exc:
        pytest.fail(
            f"Rule '{RULE_ID}' is not registered in any convention: {exc} "
            "Declare it in its single-node home "
            f"src/atdd/planner/conventions/nodes/{_NODE_FILENAME} — do NOT add it "
            "back to CONDUCTOR.md (that would re-introduce the dual-source-of-truth "
            "pattern removed by the Coach Decomposition #887)."
        )
    assert meta.rule_id == RULE_ID

    node_path = (
        Path(__file__).parent.parent  # src/atdd/planner
        / "conventions"
        / "nodes"
        / _NODE_FILENAME
    )
    assert node_path.exists(), (
        f"Rule '{RULE_ID}' resolves but its canonical single-node home "
        f"{node_path} is missing."
    )


def test_installed_wmbt_convention_ships_must_have_smoke_acceptance_rule() -> None:
    """SMOKE: the rule's single-node convention file ships in the installed package.

    The rule's canonical home is its ``nodes/`` single-node convention file;
    that is what must survive the build-and-install pipeline (replacing the prior
    CONDUCTOR.md / monolith-rules-block check).
    """
    # ``atdd.planner.conventions`` is a namespace package, so __file__ is None
    # and we resolve the directory via __path__.
    conventions_module = importlib.import_module("atdd.planner.conventions")
    conv_dir = Path(next(iter(conventions_module.__path__)))
    node_path = conv_dir / "nodes" / _NODE_FILENAME
    assert node_path.exists(), (
        f"Installed package does not ship the rule's single-node convention "
        f"{node_path}. The rule did not survive the build-and-install pipeline."
    )
