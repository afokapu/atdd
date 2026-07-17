# URN: component:validate-conventions:tune-convention-suite:graph-mutations:backend:domain
# Runtime: python
# Purpose: Generic convention-graph fault injection for the suite (#1415, E033; #1416, E034; #1458, E035).
"""Inject convention-graph faults without ever writing the real checkout (#1415).

Fault-injection tests historically rewrote a real ``*.convention.yaml`` on disk, evaluated
the family template, then reverted in a ``finally``. That cost THREE graph builds per
variant (pre-state, faulted, post-revert) and mutated the working tree, which blocks
parallelism and risks a residue if the revert is skipped.

These helpers inject the SAME semantic fault into a deep copy of the already-composed
graph instead. The shared session ``clean_convention_graph`` (#1414, E032) is never
touched and no rebuild is triggered.

The helpers are deliberately GENERIC — they name no family. Phase B (#1415) added
``clone_graph`` + ``rename_rule_id`` for ``binding``; Phase C (#1416) adds the field/ref/
node primitives the coherence, presence, resolution, coverage, and acyclicity evaluator
faults need. Nothing here hardcodes a family: every helper takes a node id (or a Node)
and mutates the clone in place, so the caller — never this module — decides which real
node to fault. Callers pass a :func:`clone_graph` result; passing the shared session
graph would leak the fault into every other test.

Phase D (#1458, E035) adds the ROOT-REDIRECT primitives — ``graph_rooted_at``,
``mirror_file``, ``stage_file``, ``staged_tree`` — for the second evaluator shape. Not
every evaluator reads its fault from a node: the policy hook/suppression scanners, the
grammar and schema whole-file readers, and the composition package-data reader take the
graph purely as a carrier for ``.root`` and then read real files off disk. Those faults
have no node to mutate and must be real files — but they still need not touch the real
checkout. Stage the fault in a temp tree built from the real file's own bytes and point
a copied graph's ``.root`` at it. See the section header below for the full argument.

Between the two, no fault family in the suite has to rewrite the working tree.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Union

from atdd.validators.conventions._support.graph_loader import ConventionGraph, Node

# A field path into ``Node.fields``: a bare key, or a sequence of keys descending
# through nested mappings (e.g. ``("metadata", "disposition")``).
FieldPath = Union[str, Sequence[str]]


def _as_path(path: FieldPath) -> tuple:
    return (path,) if isinstance(path, str) else tuple(path)


def clone_graph(graph: ConventionGraph) -> ConventionGraph:
    """Return a deep copy so a caller can mutate node ids without touching the shared graph.

    ``deepcopy`` reproduces the graph's internal aliasing: the ``Node`` reached via
    ``_by_id[id]`` is the SAME object as its entry in ``_nodes``, so a later id rename
    stays consistent across both views. No file is read — this is pure in-memory work,
    far cheaper than another ``load_composed_graph`` build.
    """
    return copy.deepcopy(graph)


def rename_rule_id(
    graph: ConventionGraph, old_id: str, suffix: str = "-PARITYBROKEN"
) -> str:
    """Rename a rule node's DECLARATION id in place, leaving the emission index untouched.

    This is the injected declaration<->implementation roundtrip break, semantically
    identical to the on-disk ``rule_id:`` rewrite it replaces: the rule's declaration id
    moves to ``old_id + suffix`` while its ``bind_rule(old_id)`` emission — recorded in
    ``_emits`` by the source scan, NOT by the rule declaration — does not. The emitted
    identity therefore no longer resolves back to the declaring rule, and the roundtrip
    template flags exactly that rule.

    Mutates ``graph`` directly, so callers pass a :func:`clone_graph` result — never the
    shared session graph. Returns the new (broken) id.

    Raises ``KeyError`` if ``old_id`` names no node, so a drifted rule id fails loudly
    rather than injecting a no-op fault the caller would read as a vacuous pass.
    """
    node = graph.by_id(old_id)
    if node is None:
        raise KeyError(f"rule id {old_id!r} not present in graph")
    new_id = f"{old_id}{suffix}"
    node.id = new_id
    # Re-key the declaration index; _emits is deliberately left as-is — that gap IS the fault.
    del graph._by_id[old_id]
    graph._by_id[new_id] = node
    return new_id


def _require(graph: ConventionGraph, node_id: str) -> Node:
    node = graph.by_id(node_id)
    if node is None:
        raise KeyError(f"node id {node_id!r} not present in graph")
    return node


def node_at(graph: ConventionGraph, location: str) -> Node:
    """Return the single node loaded from ``location`` (a repo-relative source path).

    The bridge from the old mechanism to the new one: a filesystem fault named its
    target by the FILE it rewrote, while a node fault must name a node id. Every node
    records the path it was loaded from in ``Node.location``, so the same anchor —
    ``plan/integrate_end_to_end/D001.yaml`` — still selects the same target, and a
    moved or renamed source file raises instead of silently faulting nothing.

    Raises ``KeyError`` if no node was loaded from ``location``, and ``ValueError`` if
    several were (an ambiguous anchor must not resolve arbitrarily).
    """
    matches = [n for n in graph.nodes() if n.location == location]
    if not matches:
        raise KeyError(f"no node was loaded from {location!r}")
    if len(matches) > 1:
        raise ValueError(
            f"{location!r} loaded {len(matches)} nodes ({[n.id for n in matches]}); "
            "the anchor is ambiguous — name the node id directly"
        )
    return matches[0]


def set_node_field(graph: ConventionGraph, node_id: str, path: FieldPath, value: Any) -> Node:
    """Set ``node.fields[path] = value`` on the clone, creating intermediate dicts.

    The presence/coherence evaluators read a node's declared payload straight from
    ``Node.fields`` (e.g. a rule's ``fix_hint``, a train's ``family``), so overwriting
    that value in memory injects the SAME fault the on-disk YAML rewrite produced — with
    no file touched. ``path`` is a bare key or a sequence descending nested mappings.

    Raises ``KeyError`` if ``node_id`` names no node, and ``TypeError`` if the path runs
    through a non-mapping — a drifted shape fails loudly rather than injecting a no-op.
    Returns the mutated node.
    """
    node = _require(graph, node_id)
    keys = _as_path(path)
    cursor = node.fields
    for key in keys[:-1]:
        nxt = cursor.get(key)
        if nxt is None:
            nxt = {}
            cursor[key] = nxt
        elif not isinstance(nxt, dict):
            raise TypeError(f"field path {keys!r} descends through non-mapping at {key!r}")
        cursor = nxt
    cursor[keys[-1]] = value
    return node


def remove_node_field(graph: ConventionGraph, node_id: str, path: FieldPath) -> Any:
    """Delete a (possibly nested) key from ``node.fields`` on the clone; return its value.

    Injects a MISSING-field fault — the presence ``required_field_presence`` evaluator
    flags a node whose required key is absent, exactly what dropping the key from the real
    convention YAML did. Raises ``KeyError`` if the node or the field is absent, so a
    drifted schema cannot silently inject a vacuous (already-absent) fault the caller would
    read as a pass.
    """
    node = _require(graph, node_id)
    keys = _as_path(path)
    cursor = node.fields
    for key in keys[:-1]:
        cursor = cursor.get(key) if isinstance(cursor, dict) else None
        if not isinstance(cursor, dict):
            raise KeyError(f"field path {keys!r} not present in node {node_id!r}")
    if not isinstance(cursor, dict) or keys[-1] not in cursor:
        raise KeyError(f"field {keys!r} not present in node {node_id!r}")
    return cursor.pop(keys[-1])


def break_ref(graph: ConventionGraph, node_id: str, old_ref: str, new_ref: str) -> Node:
    """Repoint one of a node's outgoing references so it dangles, on the clone.

    Resolution evaluators walk ``node.refs`` (and the same urns mirrored in
    ``node.fields``) and flag a reference that resolves to no node. Rewriting a live ref
    to ``new_ref`` (an id present in no graph node) reproduces the broken-URN fault the
    on-disk manifest patch injected. Both the ``refs`` list and any matching string leaf
    under ``fields`` are repointed so evaluators reading either representation see the
    break.

    Raises ``KeyError`` if the node is absent or does not carry ``old_ref`` in ``refs`` —
    a drifted ref fails loudly instead of injecting nothing. Returns the mutated node.
    """
    node = _require(graph, node_id)
    if old_ref not in node.refs:
        raise KeyError(f"ref {old_ref!r} not in refs of node {node_id!r}: {node.refs}")
    node.refs = [new_ref if r == old_ref else r for r in node.refs]
    _rewrite_value_in_fields(node.fields, old_ref, new_ref)
    return node


def replace_field_value(graph: ConventionGraph, node_id: str, old_value: str, new_value: str) -> int:
    """Rewrite every ``old_value`` string leaf to ``new_value`` in ``node.fields``.

    Some references live only in ``Node.fields`` — a produced contract URN under
    ``produce[].contract``, a schema id nested in a payload — never in ``node.refs``. The
    resolution/schema evaluators read those directly, so repointing the value in memory
    injects the SAME unresolvable-reference fault the on-disk manifest patch produced.

    Returns the number of leaves rewritten. Raises ``KeyError`` if the node is absent or
    the value appears nowhere, so a drifted anchor injects no vacuous no-op fault.
    """
    node = _require(graph, node_id)
    count = _rewrite_value_in_fields(node.fields, old_value, new_value)
    if count == 0:
        raise KeyError(f"value {old_value!r} not present in fields of node {node_id!r}")
    return count


def _rewrite_value_in_fields(obj: Any, old_value: str, new_value: str) -> int:
    """Replace every ``old_value`` string leaf with ``new_value``; return the count."""
    count = 0
    if isinstance(obj, dict):
        for key, val in obj.items():
            if val == old_value:
                obj[key] = new_value
                count += 1
            else:
                count += _rewrite_value_in_fields(val, old_value, new_value)
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            if val == old_value:
                obj[i] = new_value
                count += 1
            else:
                count += _rewrite_value_in_fields(val, old_value, new_value)
    return count


def add_node(
    graph: ConventionGraph,
    *,
    id: str,
    kind: str,
    location: str = "<in-memory-fault-node>",
    package: Optional[str] = None,
    theme: Optional[str] = None,
    refs: Optional[Sequence[str]] = None,
    validator: Optional[str] = None,
    fields: Optional[dict] = None,
) -> Node:
    """Append a synthetic ``Node`` to the clone, mirroring what the loader would build.

    Several coverage/acyclicity faults were injected by DROPPING a new ``*.yaml`` into the
    tree (an orphan rule, a WMBT with no SMOKE acceptance, a produce/consume cycle) so the
    rebuilt graph would carry the offending node. The same node can be constructed directly
    from the same fields the loader reads (``kind``/``fields``/``refs``), added to the clone,
    and evaluated — no file, no rebuild.

    ``location`` defaults to a non-existent sentinel path: an evaluator that reads a node's
    source file for an inline-suppression marker gets an ``OSError`` it already treats as
    "not suppressed", which is the correct reading for a freshly-injected fault node. When a
    fault genuinely depends on file contents at ``location`` (a real suppression marker),
    that test is a loader test and stays on disk — it must not use this helper.

    Raises ``KeyError`` if ``id`` already names a node (``ConventionGraph._add`` would
    silently drop the duplicate via ``setdefault``, injecting a vacuous no-op). Returns the
    added node.
    """
    if graph.by_id(id) is not None:
        raise KeyError(f"node id {id!r} already present — add_node would be a no-op")
    node = Node(
        id=id,
        kind=kind,
        location=location,
        package=package,
        theme=theme,
        refs=list(refs or []),
        validator=validator,
        fields=dict(fields or {}),
    )
    graph._add(node)
    return node


# ---------------------------------------------------------------------------
# Root redirection — for evaluators that read the FILESYSTEM via ``graph.root``
# (#1458, E035).
#
# The primitives above inject a fault into a node, which works only when the
# evaluator reads the fault FROM a node. A second, equally common evaluator shape
# does not: it takes the graph purely as a carrier for ``.root`` and then reads
# real files off disk — the policy hook/suppression scanners, the grammar and
# schema readers of a whole convention/registry YAML, the composition reader of
# pyproject's package-data globs. For those there is no node to mutate, and the
# fault MUST be a real file the evaluator really parses.
#
# That does NOT mean they have to rewrite the working tree, which is what they
# historically did (write the real file -> rebuild the graph -> evaluate -> revert
# in a ``finally``). The evaluator never looks at ``root``'s identity; it just
# scans whatever directory it is handed. So the fault can be staged in a temp tree
# built from the REAL file's own bytes at its REAL relative path, and the graph can
# be re-pointed at that tree. Same evaluator, same code path, same bytes, same
# layout — only the directory differs. No rebuild, and the real checkout is never
# written, so a SIGKILL mid-test can no longer leave a corrupted convention YAML,
# hook, or committed test file behind.
# ---------------------------------------------------------------------------


def graph_rooted_at(graph: ConventionGraph, root: Union[str, Path]) -> ConventionGraph:
    """Return a copy of ``graph`` whose ``.root`` points at ``root``.

    For evaluators that reach the filesystem through ``graph.root``. The copy is
    STRUCTURAL, not deep: ``_nodes`` and ``_by_id`` are fresh containers holding the
    same ``Node`` objects, so :func:`add_node` on the result cannot leak a node into
    the shared session graph, while the tens of thousands of real nodes are shared by
    reference rather than deep-copied. Building the copy is microseconds against the
    ~2.7s a ``load_composed_graph`` rebuild costs.

    The shared ``Node`` objects are therefore READ-ONLY to the caller. A test that
    needs to both mutate an existing node's fields AND redirect the root must deep
    copy first::

        g = graph_rooted_at(clone_graph(clean), tmp_path)

    Passing the session graph itself is safe here precisely because this returns a
    copy — the caller's ``.root`` change is never visible to another test.
    """
    clone = copy.copy(graph)
    clone._nodes = list(graph._nodes)
    clone._by_id = dict(graph._by_id)
    clone.root = Path(root)
    return clone


def mirror_file(
    real_root: Union[str, Path],
    staged_root: Union[str, Path],
    rel: str,
    transform: Optional[Callable[[str], str]] = None,
) -> Path:
    """Copy ``real_root/rel`` to ``staged_root/rel``, optionally faulting the copy.

    The staged tree is built from the REAL file's own bytes at its REAL relative path,
    so an evaluator pointed at ``staged_root`` (see :func:`graph_rooted_at`) parses
    exactly what it would have parsed in the checkout — the fault ``transform``
    introduces is then the ONLY difference. That is what makes the redirect faithful
    rather than a re-implementation of the substrate in a fixture.

    ``transform`` receives the real file's text and returns the faulted text. It MUST
    change something: a transform that returns its input unchanged means the fault
    anchor has drifted out of the real file, and the test would go vacuously green
    against an un-faulted tree. That raises ``ValueError`` rather than passing.

    Raises ``FileNotFoundError`` if ``rel`` does not exist in the real tree. Returns
    the staged path.
    """
    src = Path(real_root) / rel
    if not src.is_file():
        raise FileNotFoundError(f"cannot mirror {rel!r}: not a file under {real_root}")
    text = src.read_text(encoding="utf-8")
    if transform is not None:
        faulted = transform(text)
        if faulted == text:
            raise ValueError(
                f"fault transform left {rel!r} unchanged — the anchor has drifted out of "
                "the real file and the injected fault would be vacuous"
            )
        text = faulted
    dst = Path(staged_root) / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    return dst


def stage_file(staged_root: Union[str, Path], rel: str, content: str) -> Path:
    """Write ``content`` to ``staged_root/rel``, creating parents; return the path.

    For a fault whose substrate is a file that does NOT exist in the real tree — a new
    source file carrying a stale suppression marker, a synthetic wagon's module — where
    :func:`mirror_file` has nothing to copy. The historic mechanism dropped exactly such
    a file into the real checkout and unlinked it in a ``finally``; staging it under a
    temp root instead is the same substrate with no residue to sweep.
    """
    dst = Path(staged_root) / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")
    return dst


def staged_tree(staged_root: Union[str, Path], files: Mapping[str, str]) -> Path:
    """Materialize ``{relpath: content}`` under ``staged_root``; return the root."""
    for rel, content in files.items():
        stage_file(staged_root, rel, content)
    return Path(staged_root)
