# URN: component:bind-extension-conventions:binding-gap-inventory:backend:domain
# Runtime: python
# Purpose: Name the gap between the declared extension convention nodes and the
#          binding lock in BOTH directions — every declared-but-unbound obligation
#          and every bound-but-undeclared phantom — and split the unbound side into
#          gating obligations and documentation-only exemptions. Pure domain: the
#          partition is pure data; the loaders read committed files only.
"""Binding-gap inventory (#1426 WMBT L001).

The binding lock is meant to be a faithful projection of the obligations that
gate, but it is a lossy one: 50 extension convention nodes are declared while
only 26 are bound, and the two sets are not nested. Before anything can be bound
the gap must be NAMED, and named in both directions:

* **declared-but-unbound** — a convention obligation with no bound mechanism.
  Split into the GATING obligations (``strict`` / ``advisory`` /
  ``suppress-and-clean``) that must be realized and the ``documentation-only``
  nodes that carry no verdict and are exempt.
* **bound-but-undeclared** — a phantom: a bound entry no extension node declares
  (today the four ``tester.*`` detectors whose node lives in core).

:func:`compute_binding_gap` is the pure partition over a declared-with-disposition
map and a bound set; :func:`live_binding_gap` runs it over the toolkit's own
committed ``.atdd`` tree.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import yaml

from atdd.enforce.dispositions import (
    ADVISORY,
    DOCUMENTATION_ONLY,
    STRICT,
    SUPPRESS_AND_CLEAN,
)

_log = logging.getLogger(__name__)

_CONVENTION_SUFFIX = ".convention.yaml"

#: Dispositions that GATE — a node carrying one of these must be realized by a
#: bound mechanism. ``documentation-only`` is deliberately absent: it carries no
#: verdict (see :func:`atdd.enforce.dispositions.fails_on_violation`), so an
#: unbound documentation-only node is an exemption, not a coverage gap.
GATING_DISPOSITIONS = frozenset({STRICT, ADVISORY, SUPPRESS_AND_CLEAN})


@dataclass(frozen=True)
class BindingGap:
    """The three-way partition of (declared, bound) plus the unbound split.

    ``overlap`` / ``declared_not_bound`` / ``bound_not_declared`` are the
    partition; ``gating_unbound`` and ``doc_only_unbound`` split
    ``declared_not_bound`` by disposition (exhaustive and disjoint over the
    treatment vocabulary).
    """

    overlap: frozenset
    declared_not_bound: frozenset
    bound_not_declared: frozenset
    gating_unbound: frozenset
    doc_only_unbound: frozenset


def compute_binding_gap(declared: Mapping[str, str], bound: Iterable[str]) -> BindingGap:
    """Partition the declared nodes and bound conventions, naming every member.

    ``declared`` maps a convention id to its treatment disposition; ``bound`` is
    the set of convention ids marked ``bound`` in the lock. The partition is pure
    set algebra so it is stable regardless of which lock it is fed.
    """
    declared_ids = set(declared)
    bound_ids = set(bound)

    overlap = declared_ids & bound_ids
    declared_not_bound = declared_ids - bound_ids
    bound_not_declared = bound_ids - declared_ids

    gating_unbound = {c for c in declared_not_bound if declared[c] in GATING_DISPOSITIONS}
    doc_only_unbound = {c for c in declared_not_bound if declared[c] == DOCUMENTATION_ONLY}

    return BindingGap(
        overlap=frozenset(overlap),
        declared_not_bound=frozenset(declared_not_bound),
        bound_not_declared=frozenset(bound_not_declared),
        gating_unbound=frozenset(gating_unbound),
        doc_only_unbound=frozenset(doc_only_unbound),
    )


def load_declared_extension_nodes(substrate_home: str | Path) -> dict:
    """Map every vendored extension convention id to its treatment disposition.

    Mirrors :func:`atdd.enforce.conventions._convention_node_path` resolution:
    keyed off the ``<id>.convention.yaml`` file name, provider-agnostic. A node
    with no ``metadata.disposition`` defaults to ``strict`` — the same fail-closed
    default the runner uses.
    """
    ext_root = Path(substrate_home) / ".atdd" / "extensions"
    nodes: dict[str, str] = {}
    if not ext_root.is_dir():
        return nodes
    for node in sorted(ext_root.rglob(f"*{_CONVENTION_SUFFIX}")):
        cid = node.name[: -len(_CONVENTION_SUFFIX)]
        try:
            data = yaml.safe_load(node.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            _log.warning(
                "unreadable convention node — defaulting to strict",
                extra={"node": str(node), "error": str(exc)},
            )
            data = {}
        meta = data.get("metadata") if isinstance(data, dict) else None
        meta = meta if isinstance(meta, dict) else {}
        nodes[cid] = str(meta.get("disposition") or STRICT)
    return nodes


def load_bound_convention_ids(substrate_home: str | Path) -> set:
    """The ``convention_id`` of every ``disposition: bound`` entry in the lock.

    Returns an empty set when the lock is absent or malformed (there is nothing
    to inventory); a malformed lock is a wiring concern surfaced elsewhere.
    """
    lock_path = Path(substrate_home) / ".atdd" / "binding.lock.yaml"
    if not lock_path.is_file():
        return set()
    try:
        lock = yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        _log.warning(
            "unreadable binding.lock.yaml — empty bound set",
            extra={"lock_path": str(lock_path), "error": str(exc)},
        )
        return set()
    conventions = lock.get("conventions") if isinstance(lock, dict) else None
    conventions = conventions if isinstance(conventions, list) else []
    ids: set[str] = set()
    for conv in conventions:
        if isinstance(conv, dict) and conv.get("disposition") == "bound":
            cid = conv.get("convention_id")
            if cid:
                ids.add(str(cid))
    return ids


def live_binding_gap(substrate_home: str | Path) -> BindingGap:
    """The binding-gap inventory over the real committed substrate."""
    return compute_binding_gap(
        load_declared_extension_nodes(substrate_home),
        load_bound_convention_ids(substrate_home),
    )
