# URN: test:validate-conventions:tune-convention-suite:E034-GREEN-001-evaluator-fault-in-cloned-graph
# Acceptance: acc:validate-conventions:E034-RED-001-evaluator-fault-rewrites-plan-yaml
# Acceptance: acc:validate-conventions:E034-GREEN-001-evaluator-fault-injected-into-cloned-graph
# WMBT: wmbt:validate-conventions:E034
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""E034 — the remaining evaluator fault families inject into a cloned graph (#1416).

Phase C migrates the template-evaluator fault tests of coherence, presence, resolution,
coverage, and acyclicity off filesystem mutation. Each now injects its fault into a deep
clone of the session ``clean_convention_graph`` (#1414, E032) using the generic
``graph_mutations`` primitives, so no plan or convention YAML is rewritten.

E034-RED-001 (the retired mechanism): the fault used to be injected by rewriting a real
plan/convention YAML on disk and reverting it in a ``finally``. That mutates the working
tree — a test asserting the file is byte-identical throughout the run FAILS against it.
``test_on_disk_fault_rewrites_plan_yaml`` characterizes that hazard against the retained
coherence ``_parity.patch_file`` oracle, which is exactly what the in-memory path removes.

E034-GREEN-001 (the mechanism, not wall-clock): every Phase C primitive
(``add_node``, ``set_node_field``, ``remove_node_field``, ``break_ref``,
``replace_field_value``) mutates ONLY the clone — the source graph's ids and the on-disk
plan/convention YAML are byte-identical before and after. Build counts (evaluator families
9/10/9/7/2 -> loader floor) are reported on the PR as measured numbers, never asserted.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from atdd.validators.conventions.coherence import _parity as coherence_parity
from atdd.validators.conventions._support.graph_mutations import (
    add_node,
    break_ref,
    clone_graph,
    remove_node_field,
    replace_field_value,
    set_node_field,
)

# A real train that declares family: behavior — the coherence on-disk oracle's anchor.
_TRAIN_FILE = "plan/_trains/0002-coach-drives-lifecycle.yaml"
_TRAIN_ANCHOR = ("family: behavior", "family: delivery")


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


def _tree_hashes(root: Path) -> dict:
    """sha256 of every convention YAML under src/atdd AND every plan/ YAML, keyed by
    relative path — the full working-tree surface a filesystem fault would disturb."""
    paths = sorted((root / "src" / "atdd").rglob("*.convention.yaml"))
    paths += sorted((root / "plan").rglob("*.yaml"))
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
    }


def test_on_disk_fault_rewrites_plan_yaml() -> None:
    """E034-RED-001: the retired on-disk mechanism mutates a plan YAML mid-test.

    Proves the hazard the in-memory path removes: inside coherence ``_parity.patch_file``
    the targeted train file differs from its byte-snapshot (a byte-identical-throughout
    guard would fail here), and after the ``finally`` it is restored. Kept as a live
    characterization so the retained on-disk oracle can never silently stop writing.
    """
    root = _repo_root()
    train = root / _TRAIN_FILE
    before = train.read_bytes()

    with coherence_parity.patch_file(root, _TRAIN_FILE, *_TRAIN_ANCHOR):
        during = train.read_bytes()

    after = train.read_bytes()
    assert during != before, (
        "on-disk fault did not rewrite the plan YAML — the RED characterization is vacuous"
    )
    assert after == before, "on-disk fault left residue after its finally-revert"


def test_every_primitive_leaves_source_and_tree_untouched(clean_convention_graph) -> None:
    """E034-GREEN-001: every Phase C primitive mutates only the clone.

    Each of the five graph_mutations primitives is applied to a fresh clone against a real
    node; after all of them, the source graph's node ids are unchanged and every convention
    and plan YAML on disk is byte-identical — the injection is purely in memory.
    """
    root = _repo_root()
    clean = clean_convention_graph
    ids_before = clean.ids()
    tree_before = _tree_hashes(root)

    # add_node: a probe WMBT the clean graph does not carry
    probe = "wmbt:validate-conventions:E999-e034-probe"
    g = clone_graph(clean)
    add_node(g, id=probe, kind="wmbt", fields={"urn": probe})
    assert probe in g.ids() and probe not in clean.ids()

    # set_node_field / remove_node_field: a real single-node rule with metadata.disposition
    disp_rule = "planner.wmbt.must-have-smoke-acceptance"
    g = clone_graph(clean)
    set_node_field(g, disp_rule, ("metadata", "disposition"), "MUTATED")
    assert g.by_id(disp_rule).fields["metadata"]["disposition"] == "MUTATED"
    assert clean.by_id(disp_rule).fields["metadata"]["disposition"] != "MUTATED"
    g = clone_graph(clean)
    remove_node_field(g, disp_rule, ("metadata", "disposition"))
    assert "disposition" not in g.by_id(disp_rule).fields["metadata"]
    assert "disposition" in clean.by_id(disp_rule).fields["metadata"]

    # break_ref: a real train participant reference
    train = next(t for t in clean.by_kind("train") if t.refs)
    live_ref = train.refs[0]
    g = clone_graph(clean)
    break_ref(g, train.id, live_ref, f"{live_ref}-broken-xyz")
    assert f"{live_ref}-broken-xyz" in g.by_id(train.id).refs
    assert live_ref in clean.by_id(train.id).refs

    # replace_field_value: a real produced contract URN nested in a wagon's fields
    wagon = next(
        w for w in clean.by_kind("wagon")
        for item in (w.fields.get("produce") or [])
        if isinstance(item, dict) and item.get("contract")
    )
    contract_urn = next(
        item["contract"] for item in wagon.fields["produce"]
        if isinstance(item, dict) and item.get("contract")
    )
    g = clone_graph(clean)
    replace_field_value(g, wagon.id, contract_urn, f"{contract_urn}-broken")
    assert any(
        item.get("contract") == f"{contract_urn}-broken"
        for item in g.by_id(wagon.id).fields["produce"]
    )
    assert all(
        item.get("contract") != f"{contract_urn}-broken"
        for item in clean.by_id(wagon.id).fields["produce"]
    )

    # the source graph and the whole working tree are provably untouched
    assert clean.ids() == ids_before, "the session clean graph's node ids changed under injection"
    assert _tree_hashes(root) == tree_before, (
        "a convention or plan YAML changed during in-memory fault injection — the tree was written"
    )
