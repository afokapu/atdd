# URN: test:validate-conventions:tune-convention-suite:E033-GREEN-001-binding-fault-in-cloned-graph
# Acceptance: acc:validate-conventions:E033-RED-001-binding-fault-rewrites-convention-yaml
# Acceptance: acc:validate-conventions:E033-GREEN-001-binding-fault-injected-into-cloned-graph
# WMBT: wmbt:validate-conventions:E033
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""E033 — binding faults inject into a cloned graph, never onto convention YAML (#1415).

The binding family proves each variant catches a declaration<->implementation roundtrip
break by INJECTING one: a rule's declaration id is renamed while its ``bind_rule``
emission is left in place, so the emitted identity no longer resolves back to the rule.

E033-RED-001 (the retired mechanism): the fault used to be injected by rewriting a real
``*.convention.yaml`` on disk and reverting it in a ``finally``. That mutates the working
tree — a test asserting the file is byte-identical throughout the run FAILS against it.
``test_on_disk_fault_rewrites_convention_yaml`` characterizes that hazard against the
retained ``_rename_rule_id_on_disk`` oracle, which is exactly what the new path removes.

E033-GREEN-001 (the mechanism, not wall-clock): the fault is now injected by
:func:`rename_rule_id` on a :func:`clone_graph` deep copy. The roundtrip template flags
the injected rule and only it, evidence keys stay a subset of the template's
``failure_evidence``, every convention YAML under ``src/atdd`` is byte-identical before
and after, and the session ``clean_convention_graph`` is provably unmutated. Build count
(binding 13 -> 1) is reported on the PR as a measured number, never asserted.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from atdd.validators.conventions._support.graph_mutations import (
    clone_graph,
    rename_rule_id,
)
from atdd.validators.conventions.binding import _parity_support as P

# The runtime-artifacts variant, hardcoded so this gate is self-contained. If either the
# rule id or its declaring convention drifts, `_rename_rule_id_on_disk` raises loudly
# (rule id not found) rather than injecting a vacuous no-op fault.
VARIANT = "runtime_artifacts_rule_binding"
RULE_ID = "coach.pr.runtime-artifacts-blocked"
CONVENTION = "src/atdd/coach/conventions/pr.convention.yaml"


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


def _convention_hashes(root: Path) -> dict:
    """sha256 of every ``*.convention.yaml`` under src/atdd, keyed by relative path."""
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((root / "src" / "atdd").rglob("*.convention.yaml"))
    }


def test_on_disk_fault_rewrites_convention_yaml() -> None:
    """E033-RED-001: the retired on-disk mechanism mutates the convention YAML mid-test.

    Proves the hazard the in-memory path removes: inside ``_rename_rule_id_on_disk`` the
    targeted file differs from its byte-snapshot (a byte-identical-throughout guard would
    fail here), and after the ``finally`` it is restored. Kept as a live characterization
    so the retained on-disk oracle can never silently stop writing to disk.
    """
    root = _repo_root()
    conv = root / CONVENTION
    before = conv.read_bytes()

    with P._rename_rule_id_on_disk(conv, RULE_ID):
        during = conv.read_bytes()

    after = conv.read_bytes()

    assert during != before, (
        "on-disk fault did not rewrite the convention YAML — the RED characterization is "
        "vacuous; the oracle stopped mutating disk"
    )
    assert after == before, "on-disk fault left residue after its finally-revert"


def test_binding_fault_injected_into_cloned_graph(clean_convention_graph) -> None:
    """E033-GREEN-001: inject the fault into a clone; write nothing, mutate nothing shared."""
    root = _repo_root()
    clean = clean_convention_graph

    conv_before = _convention_hashes(root)
    ids_before = clean.ids()
    assert RULE_ID in ids_before, f"clean graph is missing the un-faulted rule {RULE_ID!r}"

    # the injected fault lives entirely on the deep copy
    faulted = clone_graph(clean)
    broken = rename_rule_id(faulted, RULE_ID)
    flags = P.evaluate(P._ROUNDTRIP, VARIANT, root, graph=faulted)

    # 1. the roundtrip template flags the injected rule, and ONLY it
    assert flags, "the injected binding fault was not caught on the cloned graph"
    assert all(ev.get("declaration_id") == broken for ev in flags), (
        f"flagged something other than the injected rule: {flags[:3]}"
    )
    # 2. evidence keys are a subset of the template's declared failure_evidence
    allowed = set(P._TEMPLATES[P._ROUNDTRIP].failure_evidence)
    assert all(set(ev) <= allowed for ev in flags), (
        f"evidence keys escaped the template vocabulary {sorted(allowed)}: {flags[:3]}"
    )

    # 3. every convention YAML under src/atdd is byte-identical before and after
    assert _convention_hashes(root) == conv_before, (
        "a convention YAML changed during in-memory fault injection — the tree was written"
    )
    # 4. the session clean graph is unmutated: its node ids are unchanged
    assert clean.ids() == ids_before, "the session clean graph's node ids changed under injection"
    assert broken not in clean.ids(), "the injected broken id leaked into the shared clean graph"


def test_clone_graph_is_independent_of_its_source(clean_convention_graph) -> None:
    """clone_graph must be a true deep copy: renaming a node on the clone leaves the
    source graph's id set and emission index untouched (the invariant #1416 will lean on).
    """
    src = clean_convention_graph
    src_ids = src.ids()
    src_emitters = src.emits(RULE_ID)

    clone = clone_graph(src)
    broken = rename_rule_id(clone, RULE_ID)

    assert broken in clone.ids() and RULE_ID not in clone.ids(), "rename did not take on the clone"
    # rename_rule_id leaves _emits alone — that gap IS the fault
    assert clone.emits(RULE_ID) == src_emitters, "rename_rule_id must not touch the emission index"
    # source untouched
    assert src.ids() == src_ids, "mutating the clone changed the source graph's ids"
    assert src.by_id(RULE_ID) is not None, "source lost the renamed rule — clone was shallow"
