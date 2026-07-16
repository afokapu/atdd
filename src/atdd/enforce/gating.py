# URN: component:bind-extension-conventions:gating-node-binding-validation:backend:domain
# Runtime: python
# Purpose: Keep the binding lock a faithful projection of the gating obligations —
#          fail loudly when a gating extension node has no bound mechanism, or a
#          bound entry realizes an obligation declared nowhere in the node universe
#          — while leaving documentation-only nodes exempt. Pure domain + committed
#          -file loaders; no provider spawn.
"""Gating-node binding validation (#1426 WMBT E002).

Binding the fanned-out rules is only durable if a gate keeps the lock a faithful
projection of the gating obligations. Two directions, asserted together:

1. Every GATING extension convention node — ``strict`` / ``advisory`` /
   ``suppress-and-clean`` — MUST appear as a ``bound`` entry. ``documentation-only``
   nodes (``coder.performance.perf``, ``tester.migration.naming``) carry no verdict
   and are EXEMPT, so they may stay unbound.
2. Zero bound-not-declared: every ``bound`` entry must resolve to a convention
   node declared SOMEWHERE in the node universe — core OR extensions. This is the
   full-universe check, distinct from and complementary to the extension-scoped
   orphan detector shipped by govern-providers (#1425): the four ``tester.*``
   bindings whose node lives in core are declared obligations here, not orphans,
   while a binding whose obligation is declared nowhere is caught.

Before the fan-out the first assertion fails on the 26 unbound gating nodes;
after it, both hold.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from atdd.enforce.binding_gap import (
    GATING_DISPOSITIONS,
    load_bound_convention_ids,
    load_declared_extension_nodes,
)

_CONVENTION_SUFFIX = ".convention.yaml"


class GatingCoverageError(Exception):
    """A gating node has no bound mechanism, or a binding has no declared obligation."""


def find_unbound_gating_nodes(declared: Mapping[str, str], bound: Iterable[str]) -> list:
    """Declared nodes with a gating disposition that are not bound (sorted).

    ``documentation-only`` nodes are never returned — they are exempt from
    binding.
    """
    bound_ids = set(bound)
    return sorted(
        cid
        for cid, disposition in declared.items()
        if disposition in GATING_DISPOSITIONS and cid not in bound_ids
    )


def find_undeclared_bindings(bound: Iterable[str], declared_universe: Iterable[str]) -> list:
    """Bound convention ids not present in the full declared node universe (sorted).

    ``declared_universe`` is the union of the extension and core convention node
    ids, so a binding declared only in core is accepted while one declared nowhere
    is reported.
    """
    universe = set(declared_universe)
    return sorted(cid for cid in set(bound) if cid not in universe)


def load_core_node_ids(repo_root: str | Path) -> set:
    """Every convention id declared as a core single-node file under ``src/atdd``.

    Resolution is keyed off ``<id>.convention.yaml`` files living in a
    ``conventions/nodes/`` directory, provider-agnostic and matching the core
    single-node layout (#1225).
    """
    src = Path(repo_root) / "src" / "atdd"
    ids: set[str] = set()
    if not src.is_dir():
        return ids
    for node in src.rglob(f"*{_CONVENTION_SUFFIX}"):
        if node.parent.name == "nodes" and node.parent.parent.name == "conventions":
            ids.add(node.name[: -len(_CONVENTION_SUFFIX)])
    return ids


def render_gating_report(unbound: list, undeclared: list) -> str:
    """A loud, human-readable report of the coverage faults (or a clean line)."""
    if not unbound and not undeclared:
        return (
            "gating-coverage: clean — every gating extension node is bound and every "
            "binding realizes a declared obligation."
        )
    lines: list[str] = ["gating-coverage: binding lock is not a faithful projection:"]
    for cid in unbound:
        lines.append(
            f"  [unbound-gating] {cid} — gating extension node with no bound mechanism"
        )
    for cid in undeclared:
        lines.append(
            f"  [bound-not-declared] {cid} — bound but no convention node declares it "
            "(core or extensions)"
        )
    return "\n".join(lines)


def assert_gating_coverage(substrate_home: str | Path, repo_root: str | Path) -> None:
    """Raise :class:`GatingCoverageError` on any coverage fault; else return ``None``.

    The loud guard: a gating obligation with no mechanism, or a mechanism with no
    declared obligation, must be caught here — not left to default silently to
    ``strict`` in the runner.
    """
    declared = load_declared_extension_nodes(substrate_home)
    bound = load_bound_convention_ids(substrate_home)
    universe = set(declared) | load_core_node_ids(repo_root)

    unbound = find_unbound_gating_nodes(declared, bound)
    undeclared = find_undeclared_bindings(bound, universe)
    if unbound or undeclared:
        raise GatingCoverageError(render_gating_report(unbound, undeclared))
