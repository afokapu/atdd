"""
Traceability Graph Builder
==========================
Constructs the URN traceability graph from declarations and resolutions.

The graph represents relationships between URN-identified artifacts:
- Nodes: URN declarations with optional artifact paths
- Edges: Relationships (contains, produces, consumes, implements)

Output formats:
- JSON: Machine-readable graph structure
- DOT: Graphviz visualization format
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple
from enum import Enum

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.graph.resolver import (
    ResolverRegistry,
    URNDeclaration,
    URNResolution,
)
from atdd.coach.utils.graph.urn import URNGrammar


class EdgeType(Enum):
    """Types of edges in the traceability graph."""

    CONTAINS = "contains"  # Parent-child containment (wagon contains feature)
    PRODUCES = "produces"  # Producer relationship (wagon produces contract)
    CONSUMES = "consumes"  # Consumer relationship (wagon consumes contract)
    IMPLEMENTS = "implements"  # Implementation relationship (component implements feature)
    REFERENCES = "references"  # General reference relationship
    INCLUDES = "includes"  # Train includes wagons (many-to-many)
    TRAIN_STEP = "train_step"  # Ordered wagon→wagon handoff inside a train's sequence[] (#287)
    TESTED_BY = "tested_by"  # Verification relationship (acc/component tested by test)


# Graphviz rendering (to_dot). Intentionally closed enumerations: visualization
# only, with a "#FAFAFA" / "" fallback. A new URN family or edge type renders
# with the fallback and needs no edits here.
# Audit reference: docs/urn-prefix-audit-2026.md (finding #3).
_FAMILY_COLORS = {
    "wagon": "#E3F2FD",  # Light blue
    "feature": "#E8F5E9",  # Light green
    "wmbt": "#FFF3E0",  # Light orange
    "acc": "#FCE4EC",  # Light pink
    "contract": "#F3E5F5",  # Light purple
    "telemetry": "#E0F7FA",  # Light cyan
    "train": "#FFEBEE",  # Light red
    "component": "#FFF8E1",  # Light amber
    "table": "#ECEFF1",  # Light blue-grey
    "migration": "#EFEBE9",  # Light brown
    "test": "#FCE4EC",  # Light pink
}

_EDGE_STYLES = {
    EdgeType.CONTAINS: 'style=solid, color="#2196F3"',
    EdgeType.PRODUCES: 'style=dashed, color="#4CAF50"',
    EdgeType.CONSUMES: 'style=dashed, color="#FF9800"',
    EdgeType.IMPLEMENTS: 'style=dotted, color="#9C27B0"',
    EdgeType.REFERENCES: 'style=dotted, color="#607D8B"',
    EdgeType.INCLUDES: 'style=bold, color="#F44336"',
    EdgeType.TESTED_BY: 'style=dashed, color="#E91E63"',
}


@dataclass
class URNNode:
    """
    A node in the traceability graph representing a URN-identified artifact.

    Attributes:
        urn: The URN identifier
        family: URN family (wagon, feature, wmbt, etc.)
        artifact_path: Path to the artifact file (if resolved)
        label: Human-readable label for visualization
        metadata: Additional metadata about the node
    """

    urn: str
    family: str
    artifact_path: Optional[Path] = None
    label: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Return unique node ID (the URN)."""
        return self.urn

    @property
    def display_label(self) -> str:
        """Return label for visualization."""
        if self.label:
            return self.label
        # Extract meaningful part from URN
        parts = self.urn.split(":")
        if len(parts) >= 2:
            return parts[-1]
        return self.urn

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "urn": self.urn,
            "family": self.family,
            "artifact_path": str(self.artifact_path) if self.artifact_path else None,
            "label": self.display_label,
            "metadata": self.metadata,
        }


@dataclass
class URNEdge:
    """
    An edge in the traceability graph representing a relationship.

    Attributes:
        source_urn: Source node URN
        target_urn: Target node URN
        edge_type: Type of relationship
        metadata: Additional metadata about the edge
    """

    source_urn: str
    target_urn: str
    edge_type: EdgeType
    metadata: Dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Return unique edge ID."""
        return f"{self.source_urn}--{self.edge_type.value}-->{self.target_urn}"

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "source": self.source_urn,
            "target": self.target_urn,
            "type": self.edge_type.value,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class UnresolvedReference:
    """A URN an edge points at that the graph refused to invent a node for (#1753).

    Recorded — never silently dropped. The edge that named this URN is kept, so
    the reference stays visible as a real dangling end rather than resolving
    against a node the graph fabricated moments earlier.
    """

    urn: str
    family: str
    reason: str

    def to_dict(self) -> Dict:
        return {"urn": self.urn, "family": self.family, "reason": self.reason}


class TraceabilityGraph:
    """
    The complete traceability graph with nodes and edges.

    Provides methods for:
    - Adding/removing nodes and edges
    - Querying graph structure
    - Exporting to JSON and DOT formats
    """

    def __init__(
        self,
        allowed_families: Optional[List[str]] = None,
        node_resolver: Optional[Callable[[str, str], Optional[str]]] = None,
    ):
        self._nodes: Dict[str, URNNode] = {}
        self._edges: List[URNEdge] = []
        self._edges_by_source: Dict[str, List[URNEdge]] = {}
        self._edges_by_target: Dict[str, List[URNEdge]] = {}
        self._allowed_families: Optional[Set[str]] = set(allowed_families) if allowed_families else None
        # #1753: the write-path resolver. Given (urn, family), returns None when
        # the URN resolves to a real artifact, or a reason string when it does
        # not. When absent, _ensure_node keeps its historical behaviour — used by
        # get_subgraph()/filtered copies, which only ever re-add nodes that were
        # already resolved when the source graph was built.
        self._node_resolver = node_resolver
        self._unresolved: Dict[str, UnresolvedReference] = {}

    @property
    def nodes(self) -> Dict[str, URNNode]:
        """Return all nodes indexed by URN."""
        return self._nodes.copy()

    @property
    def edges(self) -> List[URNEdge]:
        """Return all edges."""
        return self._edges.copy()

    def add_node(self, node: URNNode) -> None:
        """Add a node to the graph."""
        self._nodes[node.urn] = node

    def add_edge(self, edge: URNEdge) -> bool:
        """
        Add an edge to the graph.

        Returns False if the edge was skipped due to family filtering.
        """
        source_family = self._infer_family(edge.source_urn)
        target_family = self._infer_family(edge.target_urn)

        # Skip edges if families are filtered and source/target not in allowed list
        if self._allowed_families and not (
            source_family in self._allowed_families
            and target_family in self._allowed_families
        ):
            return False

        # Ensure source and target nodes exist
        self._ensure_node(edge.source_urn, source_family)
        self._ensure_node(edge.target_urn, target_family)

        self._edges.append(edge)
        self._edges_by_source.setdefault(edge.source_urn, []).append(edge)
        self._edges_by_target.setdefault(edge.target_urn, []).append(edge)

        return True

    def _ensure_node(self, urn: str, family: str) -> None:
        """Create a node for a URN the graph has not seen yet — if it resolves.

        #1753: this is the graph's only write path for edge endpoints, and it
        used to create a node for ANY URN handed to it, consulting no resolver.
        An edge then "resolved" against a node the graph had invented moments
        earlier — 28 phantom feature parents carrying 149 component edges.

        A fabricated node reports as resolved, which is worse than absence:
        absence is reportable. So an unresolvable URN gets NO node and is
        recorded in ``unresolved_references``. The caller still appends the
        edge, because deleting it would substitute a quieter lie for a loud one
        — ``get_children``/``get_parents``/``_contained_urns`` already skip
        endpoints with no node.
        """
        if urn in self._nodes:
            return

        if self._node_resolver is not None:
            reason = self._node_resolver(urn, family)
            if reason is not None:
                self._unresolved[urn] = UnresolvedReference(
                    urn=urn, family=family, reason=reason
                )
                return

        self._nodes[urn] = URNNode(urn=urn, family=family)

    @property
    def unresolved_references(self) -> Dict[str, UnresolvedReference]:
        """URNs an edge named that did not resolve, so no node was created (#1753)."""
        return dict(getattr(self, "_unresolved", {}))

    def __getstate__(self) -> Dict:
        """Drop the resolver before pickling (#1753).

        The write-path resolver is a closure over the builder, so it is not
        picklable — and this graph is pickled into ``.atdd/cache``. Without
        this, every cache write would raise, be swallowed by the writer's
        ``except Exception``, and silently turn a cached build back into a full
        rebuild. A restored graph is already fully built, so it needs no
        resolver; ``_ensure_node`` on it behaves like any resolver-less copy.
        """
        state = self.__dict__.copy()
        state["_node_resolver"] = None
        return state

    def __setstate__(self, state: Dict) -> None:
        # Tolerate caches pickled before this field existed.
        state.setdefault("_node_resolver", None)
        state.setdefault("_unresolved", {})
        self.__dict__.update(state)

    def _infer_family(self, urn: str) -> str:
        """Infer family from URN prefix."""
        if ":" in urn:
            return urn.split(":")[0]
        return "unknown"

    def get_node(self, urn: str) -> Optional[URNNode]:
        """Get a node by URN."""
        return self._nodes.get(urn)

    def nodes_by_family(self, family: str) -> List[URNNode]:
        """Return all nodes belonging to a given family."""
        return [n for n in self._nodes.values() if n.family == family]

    def get_outgoing_edges(self, urn: str) -> List[URNEdge]:
        """Get all edges originating from a node."""
        return self._edges_by_source.get(urn, [])

    def get_incoming_edges(self, urn: str) -> List[URNEdge]:
        """Get all edges targeting a node."""
        return self._edges_by_target.get(urn, [])

    def get_children(self, urn: str, edge_type: Optional[EdgeType] = None) -> List[URNNode]:
        """Get child nodes (targets of outgoing edges)."""
        edges = self.get_outgoing_edges(urn)
        if edge_type:
            edges = [e for e in edges if e.edge_type == edge_type]
        return [self._nodes[e.target_urn] for e in edges if e.target_urn in self._nodes]

    def get_parents(self, urn: str, edge_type: Optional[EdgeType] = None) -> List[URNNode]:
        """Get parent nodes (sources of incoming edges)."""
        edges = self.get_incoming_edges(urn)
        if edge_type:
            edges = [e for e in edges if e.edge_type == edge_type]
        return [self._nodes[e.source_urn] for e in edges if e.source_urn in self._nodes]

    def get_subgraph(
        self,
        root_urn: str,
        max_depth: int = -1,
        edge_type_exclude: Optional[Set[EdgeType]] = None,
    ) -> "TraceabilityGraph":
        """
        Extract a subgraph starting from a root node.

        Args:
            root_urn: Starting node URN
            max_depth: Maximum traversal depth (-1 for unlimited)
            edge_type_exclude: Optional set of EdgeType values to skip during
                traversal. Edges of these types are neither copied into the
                subgraph nor followed to their targets. Structural consumers
                pass ``{EdgeType.TRAIN_STEP}`` to prevent wagon-rooted
                subgraphs from leaking cross-train wagons via shared
                handoffs (#287). Defaults to None (existing behavior:
                traverse every edge).

        Returns:
            New graph containing only reachable nodes and edges
        """
        subgraph = TraceabilityGraph()
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(root_urn, 0)]
        excluded = edge_type_exclude or set()

        while queue:
            urn, depth = queue.pop(0)
            if urn in visited or (max_depth >= 0 and depth > max_depth):
                continue

            visited.add(urn)

            node = self.get_node(urn)
            if node:
                subgraph.add_node(node)

            queue.extend(self._follow_edges(subgraph, urn, depth, visited, excluded))

        return subgraph

    def _follow_edges(
        self,
        subgraph: "TraceabilityGraph",
        urn: str,
        depth: int,
        visited: Set[str],
        excluded: Set[EdgeType],
    ) -> List[Tuple[str, int]]:
        """Copy this node's outgoing edges into the subgraph; return targets to visit."""
        next_up: List[Tuple[str, int]] = []
        for edge in self.get_outgoing_edges(urn):
            if edge.edge_type in excluded:
                continue

            subgraph.add_edge(edge)
            if edge.target_urn not in visited:
                next_up.append((edge.target_urn, depth + 1))
        return next_up

    def filter_by_family(self, families: List[str]) -> "TraceabilityGraph":
        """
        Filter graph to only include nodes of specified families.

        Args:
            families: List of family names to include

        Returns:
            New filtered graph
        """
        filtered = TraceabilityGraph()

        for urn, node in self._nodes.items():
            if node.family in families:
                filtered.add_node(node)

        for edge in self._edges:
            source_node = self._nodes.get(edge.source_urn)
            target_node = self._nodes.get(edge.target_urn)
            if source_node and target_node:
                if source_node.family in families and target_node.family in families:
                    filtered.add_edge(edge)

        return filtered

    def to_agent_summary(self) -> Dict:
        """
        Produce a compact, agent-optimized summary of the traceability graph.

        Returns a dict with four sections:
        - stats: node/edge counts by family and edge type
        - tree: per-wagon breakdown of features, wmbts, coverage
        - dataflow: wagon-to-wagon data flow via shared contracts
        - gaps: orphans, unconsumed contracts, untested components/accs
        """

        tested_by_targets = {
            e.source_urn for e in self._edges if e.edge_type == EdgeType.TESTED_BY
        }
        contract_producer, contract_consumers = self._contract_flow()

        return {
            "stats": self._summary_stats(),
            "tree": self._summary_tree(tested_by_targets),
            "dataflow": self._summary_dataflow(contract_producer, contract_consumers),
            "gaps": self._summary_gaps(
                tested_by_targets, contract_producer, contract_consumers
            ),
        }

    def _contained_urns(self, source_urn: str, family: str) -> List[str]:
        """Targets of CONTAINS edges leaving source_urn whose node has this family."""
        return [
            e.target_urn
            for e in self._edges_by_source.get(source_urn, [])
            if e.edge_type == EdgeType.CONTAINS
            and self._nodes.get(e.target_urn, URNNode(urn="", family="")).family == family
        ]

    def _targets_of(self, source_urn: str, edge_type: EdgeType) -> List[str]:
        """Targets of edges of this type leaving source_urn."""
        return [
            e.target_urn
            for e in self._edges_by_source.get(source_urn, [])
            if e.edge_type == edge_type
        ]

    def _summary_stats(self) -> Dict:
        """Node and edge counts, by family and by edge type."""
        families = Counter(n.family for n in self._nodes.values())
        edge_types = Counter(e.edge_type.value for e in self._edges)

        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "families": dict(families.most_common()),
            "edge_types": dict(edge_types.most_common()),
        }

    def _summary_tree(self, tested_by_targets: Set[str]) -> Dict[str, Dict]:
        """Per-wagon breakdown, then one entry per train."""
        tree: Dict[str, Dict] = {}

        for urn, node in self._nodes.items():
            if node.family == "wagon":
                tree[urn] = self._wagon_summary(urn, node, tested_by_targets)

        for urn, node in self._nodes.items():
            if node.family != "train":
                continue
            tree[urn] = {
                "description": node.metadata.get("description", ""),
                "wagons": self._targets_of(urn, EdgeType.INCLUDES),
            }

        return tree

    def _wagon_summary(
        self, urn: str, node: URNNode, tested_by_targets: Set[str]
    ) -> Dict:
        """One wagon's features, wmbts, coverage and contract flow."""
        feature_urns = self._contained_urns(urn, "feature")
        wmbt_urns = self._contained_urns(urn, "wmbt")

        # components reachable: wagon -> feature -> component (CONTAINS chain)
        components = [
            self._nodes[c_urn]
            for f_urn in feature_urns
            for c_urn in self._contained_urns(f_urn, "component")
        ]
        # accs reachable: wagon -> wmbt -> acc (CONTAINS chain)
        accs = [
            self._nodes[a_urn]
            for w_urn in wmbt_urns
            for a_urn in self._contained_urns(w_urn, "acc")
        ]

        return {
            "description": node.metadata.get("description", ""),
            # strip the "feature:wagon:" / "wmbt:wagon:" prefix
            "features": sorted(u.split(":", 2)[-1] for u in feature_urns),
            "wmbts": sorted(u.split(":", 2)[-1] for u in wmbt_urns),
            "coverage": {
                "components": {
                    "planned": len(components),
                    "implemented": sum(1 for c in components if c.artifact_path is not None),
                    "tested": sum(1 for c in components if c.urn in tested_by_targets),
                },
                "accs": {
                    "total": len(accs),
                    "tested": sum(1 for a in accs if a.urn in tested_by_targets),
                },
            },
            "produces": sorted(self._targets_of(urn, EdgeType.PRODUCES)),
            "consumes": sorted(self._targets_of(urn, EdgeType.CONSUMES)),
        }

    def _contract_flow(self) -> Tuple[Dict[str, str], Dict[str, Set[str]]]:
        """(contract -> producing wagon, contract -> consuming wagons)."""
        producer: Dict[str, str] = {}
        consumers: Dict[str, Set[str]] = {}

        for e in self._edges:
            src_node = self._nodes.get(e.source_urn)
            if not src_node or src_node.family != "wagon":
                continue
            if e.edge_type == EdgeType.PRODUCES:
                producer[e.target_urn] = e.source_urn
            elif e.edge_type == EdgeType.CONSUMES:
                consumers.setdefault(e.target_urn, set()).add(e.source_urn)

        return producer, consumers

    @staticmethod
    def _contracts_match(produced_urn: str, consumed_urn: str) -> bool:
        """Exact URNs or colon-boundary prefixes: contract:a:b matches contract:a:b:c."""
        return (
            produced_urn == consumed_urn
            or produced_urn.startswith(consumed_urn + ":")
            or consumed_urn.startswith(produced_urn + ":")
        )

    def _summary_dataflow(
        self, contract_producer: Dict[str, str], contract_consumers: Dict[str, Set[str]]
    ) -> Dict[str, Dict]:
        """Wagon -> wagon data flow via shared contracts."""
        wagon_feeds: Dict[str, Set[str]] = {}
        for produced_urn, producer in contract_producer.items():
            for consumed_urn, consumers in contract_consumers.items():
                if not self._contracts_match(produced_urn, consumed_urn):
                    continue
                for consumer in consumers:
                    if consumer != producer:
                        wagon_feeds.setdefault(producer, set()).add(consumer)

        # Include all wagons (even those that feed nobody)
        return {
            urn: {"feeds": sorted(wagon_feeds.get(urn, set()))}
            for urn, node in self._nodes.items()
            if node.family == "wagon"
        }

    def _summary_gaps(
        self,
        tested_by_targets: Set[str],
        contract_producer: Dict[str, str],
        contract_consumers: Dict[str, Set[str]],
    ) -> Dict:
        """Orphans, unconsumed contracts, and untested components/accs."""
        # Nodes with zero incoming edges (excluding root families).
        # Root families derived from URNGrammar.SEGMENT_COUNTS (parent-it-belongs-to,
        # spec v12 §3.2): a family is a root when its segment count after the
        # prefix is 1 (no parent coordinates). Adding a new top-level family in
        # PATTERNS + SEGMENT_COUNTS automatically extends this set.
        # Audit reference: docs/urn-prefix-audit-2026.md (finding #2).
        root_families = {
            family
            for family, count in URNGrammar.SEGMENT_COUNTS.items()
            if count == 1
        }
        all_targets = {e.target_urn for e in self._edges}

        return {
            "orphan_count": sum(
                1 for urn, node in self._nodes.items()
                if node.family not in root_families and urn not in all_targets
            ),
            # produced but never consumed
            "unconsumed_contracts": sorted(
                set(contract_producer.keys()) - set(contract_consumers.keys())
            ),
            "untested_components": sum(
                1 for u, n in self._nodes.items()
                if n.family == "component" and u not in tested_by_targets
            ),
            "untested_accs": sum(
                1 for u, n in self._nodes.items()
                if n.family == "acc" and u not in tested_by_targets
            ),
            # #1753: edge endpoints that did not resolve, so no node was
            # invented for them. Previously these were fabricated and reported
            # as resolved; surfacing them here is the whole point of the fix.
            "unresolved_references": [
                r.to_dict()
                for r in sorted(
                    self.unresolved_references.values(), key=lambda r: r.urn
                )
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """
        Export graph to JSON format.

        Returns:
            JSON string representation of the graph
        """
        data = {
            "nodes": [node.to_dict() for node in self._nodes.values()],
            "edges": [edge.to_dict() for edge in self._edges],
            "metadata": {
                "node_count": len(self._nodes),
                "edge_count": len(self._edges),
                "families": list(set(n.family for n in self._nodes.values())),
            },
        }
        return json.dumps(data, indent=indent, default=str)

    def to_dict(self) -> Dict:
        """Export graph to dictionary."""
        return {
            "nodes": [node.to_dict() for node in self._nodes.values()],
            "edges": [edge.to_dict() for edge in self._edges],
            "metadata": {
                "node_count": len(self._nodes),
                "edge_count": len(self._edges),
                "families": list(set(n.family for n in self._nodes.values())),
            },
        }

    def to_dot(self, title: str = "URN Traceability Graph") -> str:
        """
        Export graph to Graphviz DOT format.

        Returns:
            DOT string for visualization
        """
        lines = [
            f'digraph "{title}" {{',
            "    rankdir=TB;",
            "    node [shape=box, style=filled];",
            "",
        ]

        # Add nodes
        for urn, node in self._nodes.items():
            color = _FAMILY_COLORS.get(node.family, "#FAFAFA")
            safe_urn = urn.replace('"', '\\"')
            safe_label = node.display_label.replace('"', '\\"')
            lines.append(
                f'    "{safe_urn}" [label="{safe_label}\\n({node.family})", fillcolor="{color}"];'
            )

        lines.append("")

        # Add edges
        for edge in self._edges:
            style = _EDGE_STYLES.get(edge.edge_type, "")
            safe_source = edge.source_urn.replace('"', '\\"')
            safe_target = edge.target_urn.replace('"', '\\"')
            lines.append(
                f'    "{safe_source}" -> "{safe_target}" [{style}, label="{edge.edge_type.value}"];'
            )

        lines.append("}")
        return "\n".join(lines)


class GraphBuilder:
    """
    Builds the traceability graph from URN declarations and manifest data.

    Scans the codebase to:
    1. Find all URN declarations
    2. Parse manifest files for produce/consume relationships
    3. Build edges based on containment and dependency patterns
    """

    _CACHE_DIR = ".atdd/cache"
    _CACHE_FILE = "graph.pickle"

    _logger = logging.getLogger(__name__)

    # Test-header scanning: legacy "# URN: acc:...", V3 "# Acceptance: acc:...",
    # and "# Tested-By:" list items. _REGEX_META_RE rejects regex patterns that
    # look like URNs.
    _URN_COMMENT_RE = re.compile(r"(?:#|//)\s*[Uu][Rr][Nn]:\s*([^\s]+)")
    _ACCEPTANCE_RE = re.compile(r"(?:#|//)\s*[Aa]cceptance:\s*([^\s]+)")
    _TESTED_BY_RE = re.compile(r"(?:#|//)\s*-\s*(test:[^\s]+)")
    _REGEX_META_RE = re.compile(r"[\[\]\(\)\*\+\?\{\}\^\$\\]")

    def __init__(self, repo_root: Optional[Path] = None, *, use_cache: bool = True):
        self.repo_root = repo_root or find_repo_root()
        self.registry = ResolverRegistry(self.repo_root)
        self.plan_dir = self.repo_root / "plan"
        self.use_cache = use_cache and not os.environ.get("ATDD_NO_CACHE")

    # ------------------------------------------------------------------
    # Disk cache helpers
    # ------------------------------------------------------------------

    def _cache_path(self) -> Path:
        return self.repo_root / self._CACHE_DIR / self._CACHE_FILE

    def _compute_cache_key(self) -> str:
        """Hash sorted mtimes of all graph-input files + atdd version."""
        import atdd

        entries: List[str] = []

        # 1-3. Declaration sources
        for subdir, pattern in (
            ("plan", "*.yaml"),
            ("contracts", "*.json"),
            ("telemetry", "*.yaml"),
        ):
            entries.extend(self._mtime_entries(self.repo_root / subdir, pattern))

        # 4. Code files with URN headers (.py, .ts, .tsx, .dart)
        entries.extend(self._urn_code_mtime_entries())

        # 5. atdd toolkit version
        entries.append(f"__version__:{atdd.__version__}")

        return hashlib.sha256("\n".join(entries).encode()).hexdigest()

    def _mtime_entries(self, directory: Path, pattern: str) -> List[str]:
        """``<relpath>:<mtime_ns>`` for each file matching pattern under directory."""
        if not directory.is_dir():
            return []

        return [
            f"{p.relative_to(self.repo_root)}:{p.stat().st_mtime_ns}"
            for p in sorted(directory.rglob(pattern))
        ]

    def _urn_code_mtime_entries(self) -> List[str]:
        """``<relpath>:<mtime_ns>`` for code files whose head carries a URN header."""
        skip_dirs = {
            ".git", "__pycache__", "node_modules", ".dart_tool",
            "build", ".pub-cache", "dist", ".next", ".nuxt", "coverage",
            ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
        }
        extensions = {".py", ".dart", ".ts", ".tsx"}

        entries: List[str] = []
        for dirpath, dirnames, filenames in os.walk(self.repo_root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fname in sorted(filenames):
                if not any(fname.endswith(ext) for ext in extensions):
                    continue

                fpath = Path(dirpath) / fname
                try:
                    head = fpath.read_bytes()[:512]
                except OSError as e:
                    self._logger.debug("Skipping unreadable source %s: %s", fpath, e)
                    continue

                if b"URN:" in head:
                    rel = fpath.relative_to(self.repo_root)
                    entries.append(f"{rel}:{fpath.stat().st_mtime_ns}")
        return entries

    def _load_cached_graph(
        self, cache_key: str
    ) -> Optional[TraceabilityGraph]:
        """Load graph from disk cache if key matches. Returns None on miss."""
        cp = self._cache_path()
        if not cp.is_file():
            return None
        try:
            with cp.open("rb") as f:
                data = pickle.load(f)
            if data.get("cache_key") == cache_key:
                self._logger.info("graph cache HIT — loading from %s", cp)
                return data["graph"]
            self._logger.info("graph cache STALE — key mismatch")
        except Exception as exc:
            self._logger.warning("graph cache CORRUPT — rebuilding (%s)", exc)
        return None

    def _save_cached_graph(
        self, graph: TraceabilityGraph, cache_key: str
    ) -> None:
        """Persist graph + cache_key to disk."""
        cp = self._cache_path()
        cp.parent.mkdir(parents=True, exist_ok=True)
        tmp = cp.with_suffix(".tmp")
        try:
            with tmp.open("wb") as f:
                pickle.dump({"cache_key": cache_key, "graph": graph}, f, protocol=5)
            tmp.replace(cp)
            self._logger.info("graph cache WRITTEN — %s", cp)
        except Exception as exc:
            self._logger.warning("graph cache write failed: %s", exc)
            tmp.unlink(missing_ok=True)

    # Families whose URNs are declared by a header inside the artifact itself.
    # For these the declaration index IS the authoritative resolution — the same
    # insight as #1753 defect 2 — so "not declared" means "not real", and the
    # layout-guessing fallback in their resolvers must not get a second vote.
    # It also keeps the write path affordable: a single `test` resolve costs
    # ~4.4s and a `component` resolve ~3.1s (measured), against ~200 undeclared
    # endpoints, which would add >10 minutes to every graph build.
    _SELF_DECLARING_FAMILIES = frozenset({"test", "component"})

    def _edge_endpoint_reason(
        self,
        resolve_cache: Dict[str, URNResolution],
        declared_urns: Set[str],
    ) -> Callable[[str, str], Optional[str]]:
        """The graph's write-path resolver (#1753).

        Returns a callable answering "may a node be created for this URN?" —
        ``None`` to allow, or a reason string to refuse.

        Order matters, cheapest and most authoritative first:

        1. **Declared on disk** — the declaration pass already found an artifact
           carrying this URN. O(1), and the strongest possible evidence.
        2. **Self-declaring family** (see ``_SELF_DECLARING_FAMILIES``) — not
           declared means not real; refuse without a filesystem walk.
        3. **Anything else** — a real ``registry.resolve()``, memoised in the
           shared ``resolve_cache``. These are cheap (feature ~1ms, wagon
           ~0.1ms, acc ~0.3ms, subject ~9ms, contract ~68ms).

        A family with no registered resolver is ALLOWED, and logs that it was.
        No resolution was performed, so the URN cannot honestly be called
        unresolvable. That is a narrow remaining hole — a consumer repo defining
        its own family gets the old create-anything behaviour for it — recorded
        here rather than papered over. Every family this repo synthesizes
        (feature, subject, wagon, contract, test, acc, component) has a resolver.
        """

        def reason(urn: str, family: str) -> Optional[str]:
            if urn in declared_urns:
                return None

            if family in self._SELF_DECLARING_FAMILIES:
                return f"no file declares {family} URN: {urn}"

            if not self.registry.get_resolver(family):
                self._logger.debug(
                    "no resolver for family %r; node for %s created unverified",
                    family, urn,
                )
                return None

            if urn not in resolve_cache:
                resolve_cache[urn] = self.registry.resolve(urn)
            resolution = resolve_cache[urn]
            if resolution.is_resolved:
                return None
            return resolution.error or f"{family} URN did not resolve: {urn}"

        return reason

    def build(self, families: Optional[List[str]] = None) -> TraceabilityGraph:
        """
        Build the complete traceability graph.

        Args:
            families: Optional list of families to include. If None, includes all.

        Returns:
            Complete traceability graph
        """
        # Disk cache: check before expensive build
        cache_key: Optional[str] = None
        if self.use_cache and families is None:
            t0 = time.monotonic()
            cache_key = self._compute_cache_key()
            cached = self._load_cached_graph(cache_key)
            if cached is not None:
                elapsed = time.monotonic() - t0
                self._logger.info("graph loaded from cache in %.2fs", elapsed)
                return cached

        # Phase 1: resolve() cache — each unique URN resolved once. Shared with
        # the write-path resolver below so an edge endpoint costs no extra walk.
        resolve_cache: Dict[str, URNResolution] = {}

        # Phase 2: Single-walk multi-resolver dispatch (reads each code file once)
        declarations, content_cache = self.registry.find_all_declarations_single_pass(
            families
        )

        # Every URN some artifact on disk declares. This is the write-path
        # resolver's first and strongest test, so it must be complete BEFORE any
        # edge is added (#1753).
        declared_urns: Set[str] = {
            decl.urn for decls in declarations.values() for decl in decls
        }

        graph = TraceabilityGraph(
            allowed_families=families,
            node_resolver=self._edge_endpoint_reason(resolve_cache, declared_urns),
        )

        for family, decls in declarations.items():
            for decl in decls:
                if decl.urn not in resolve_cache:
                    resolve_cache[decl.urn] = self.registry.resolve(decl.urn)

                graph.add_node(
                    self._node_for(decl, family, resolve_cache[decl.urn])
                )

        # 2. Build edges from manifest relationships
        self._build_containment_edges(graph)
        self._build_produce_consume_edges(graph)
        self._build_train_edges(graph)
        self._build_subject_edges(graph)
        self._build_component_edges(graph)
        self._build_security_edges(graph)
        # Phase 3: pass content cache to edge builders that read files
        self._build_test_edges(graph, content_cache)
        self._build_tested_by_edges(graph, content_cache)
        self._build_journey_test_edges(graph, content_cache)
        self._build_jel_contract_nodes(graph)

        # Disk cache: persist for next run
        if cache_key is not None:
            self._save_cached_graph(graph, cache_key)

        return graph

    @staticmethod
    def _node_for(decl, family: str, resolution: URNResolution) -> URNNode:
        """The graph node for one URN declaration and its resolution."""
        metadata = {
            "source_path": str(decl.source_path),
            "is_broken": resolution.is_broken,
            "resolution_error": resolution.error,
            "is_deterministic": resolution.is_deterministic,
            "is_resolved": resolution.is_resolved,
            "resolved_paths": [str(p) for p in resolution.resolved_paths],
        }
        # Surface declaration- and resolution-level metadata onto the graph node
        # so downstream consumers (validators, viz) can read e.g. abuse_case
        # fields without re-parsing YAMLs.
        if getattr(decl, "metadata", None):
            metadata["declaration"] = dict(decl.metadata)
        if getattr(resolution, "metadata", None):
            metadata["resolution"] = dict(resolution.metadata)

        return URNNode(
            urn=decl.urn,
            family=family,
            artifact_path=(
                resolution.resolved_paths[0] if resolution.resolved_paths else None
            ),
            metadata=metadata,
        )

    def _build_containment_edges(self, graph: TraceabilityGraph) -> None:
        """Build containment edges (wagon -> feature -> wmbt -> acceptance)."""
        if not self.plan_dir.exists():
            return

        # Wagon contains features (feature:wagon:feature-name) and
        # WMBTs (wmbt:wagon:STEP001) — the wagon is the URN's first coordinate.
        self._link_wagon_children(graph, "feature")
        self._link_wagon_children(graph, "wmbt")

        # WMBT contains acceptances
        for acc_decl in graph.nodes.values():
            if acc_decl.family != "acc":
                continue

            # Parse wagon and wmbt from acc URN: acc:wagon:WMBT-HARNESS-SEQ
            parts = acc_decl.urn.replace("acc:", "").split(":")
            if len(parts) < 2:
                continue

            wmbt_id = parts[1].split("-")[0]
            graph.add_edge(URNEdge(
                source_urn=f"wmbt:{parts[0]}:{wmbt_id}",
                target_urn=acc_decl.urn,
                edge_type=EdgeType.CONTAINS,
                metadata={"source": "urn-structure"},
            ))

    @staticmethod
    def _link_wagon_children(graph: TraceabilityGraph, family: str) -> None:
        """Wagon CONTAINS every node of this family, per the node's URN structure."""
        for node in graph.nodes.values():
            if node.family != family:
                continue

            parts = node.urn.replace(f"{family}:", "").split(":")
            if len(parts) < 2:
                continue

            graph.add_edge(URNEdge(
                source_urn=f"wagon:{parts[0]}",
                target_urn=node.urn,
                edge_type=EdgeType.CONTAINS,
                metadata={"source": "urn-structure"},
            ))

    def _resolve_contract_ref(self, contract_ref: str) -> Optional[str]:
        """
        Resolve a contract reference to a URN.

        Handles:
        - URN format (contract:theme:domain...) - returned as-is
        - File path (contracts/...) - reads $id from schema
        - Schema ID (theme:domain...) - prefixed with contract:
        """
        if not contract_ref:
            return None

        # Already a contract URN
        if contract_ref.startswith("contract:"):
            return contract_ref

        # File path - resolve via $id
        if contract_ref.startswith("contracts/") or contract_ref.endswith(".schema.json"):
            return self._contract_urn_from_schema(self.repo_root / contract_ref)

        # Schema ID - prefix with contract:
        return f"contract:{contract_ref}"

    def _contract_urn_from_schema(self, contract_path: Path) -> Optional[str]:
        """The contract URN a schema file's ``$id`` names. None when it names none."""
        import json

        if not contract_path.exists():
            return None

        try:
            with open(contract_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self._logger.debug("Skipping unreadable contract schema %s: %s", contract_path, e)
            return None

        schema_id = data.get("$id") if isinstance(data, dict) else None
        # Skip urn:jel:* IDs
        if schema_id and not schema_id.startswith("urn:jel:"):
            return f"contract:{schema_id}"
        return None

    def _resolve_telemetry_ref(self, telemetry_ref: str) -> Optional[str]:
        """Resolve a telemetry reference to a URN."""
        if not telemetry_ref:
            return None

        # Already a telemetry URN
        if telemetry_ref.startswith("telemetry:"):
            return telemetry_ref

        # Schema ID - prefix with telemetry:
        return f"telemetry:{telemetry_ref}"

    def _build_produce_consume_edges(self, graph: TraceabilityGraph) -> None:
        """Build produce/consume edges from wagon manifests."""
        if not self.plan_dir.exists():
            return

        for manifest_path in self.plan_dir.rglob("_*.yaml"):
            try:
                data = self._load_yaml_mapping(manifest_path)
                if not data:
                    continue

                wagon_slug = data.get("wagon")
                if not wagon_slug:
                    continue

                wagon_urn = f"wagon:{wagon_slug}"
                self._annotate_description(graph, wagon_urn, data)
                self._add_flow_edges(graph, wagon_urn, data, EdgeType.PRODUCES)
                self._add_flow_edges(graph, wagon_urn, data, EdgeType.CONSUMES)
            except Exception as e:
                self._logger.debug(
                    "Skipping malformed wagon manifest %s: %s", manifest_path, e
                )
                continue

    def _add_flow_edges(
        self,
        graph: TraceabilityGraph,
        wagon_urn: str,
        data: dict,
        edge_type: EdgeType,
    ) -> None:
        """Edges for every contract/telemetry item in the produce[] or consume[] block."""
        block = "produce" if edge_type == EdgeType.PRODUCES else "consume"

        for item in data.get(block, []):
            contract_urn = self._flow_contract_urn(item, edge_type)
            if contract_urn:
                graph.add_edge(URNEdge(
                    source_urn=wagon_urn,
                    target_urn=contract_urn,
                    edge_type=edge_type,
                ))

            self._add_telemetry_edges(graph, wagon_urn, item.get("telemetry"), edge_type)

    def _flow_contract_urn(self, item: dict, edge_type: EdgeType) -> Optional[str]:
        """The contract a produce/consume item names.

        On produce an explicit ``urn:`` wins over the contract ref; consume has
        no such override.
        """
        if edge_type == EdgeType.PRODUCES:
            declared = item.get("urn")
            if declared and declared.startswith("contract:"):
                return declared

        return self._resolve_contract_ref(item.get("contract"))

    def _add_telemetry_edges(
        self,
        graph: TraceabilityGraph,
        wagon_urn: str,
        telemetry_ref,
        edge_type: EdgeType,
    ) -> None:
        """One edge per telemetry signal a produce/consume item names."""
        if not telemetry_ref:
            return

        refs = telemetry_ref if isinstance(telemetry_ref, list) else [telemetry_ref]
        for ref in refs:
            telemetry_urn = self._resolve_telemetry_ref(ref)
            if telemetry_urn:
                graph.add_edge(URNEdge(
                    source_urn=wagon_urn,
                    target_urn=telemetry_urn,
                    edge_type=edge_type,
                ))

    def _iter_train_files(self, trains_dir: Path) -> "list[tuple[str, Path]]":
        """Yield ``(train_urn, path)`` for every real train under ``trains_dir``.

        Typed trains (#1421) live at ``plan/_trains/<subject>/<slug>.yaml`` and
        their URN is reconstructed from the nested path, so a flat glob misses
        them entirely. Legacy flat files are still enumerated during the
        migration window.

        Underscore-prefixed entries are registry/alias artifacts —
        ``_aliases.yaml``, ``_interlockings/`` — NOT trains. They declare no
        ``train_id``, so treating one as a train detail file would mint a bogus
        URN from its stem. This mirrors the same skip in ``TrainResolver``.
        """
        found: "list[tuple[str, Path]]" = []

        for subject_dir in sorted(trains_dir.iterdir()):
            if not subject_dir.is_dir() or subject_dir.name.startswith("_"):
                continue
            for train_file in sorted(subject_dir.glob("*.yaml")):
                if train_file.name.startswith("_"):
                    continue
                found.append(
                    (f"train:{subject_dir.name}:{train_file.stem}", train_file)
                )

        for train_file in sorted(trains_dir.glob("*.yaml")):
            if train_file.name.startswith("_"):
                continue
            found.append((f"train:{train_file.stem}", train_file))

        return found

    def _build_train_edges(self, graph: TraceabilityGraph) -> None:
        """Build train -> wagon containment edges."""
        trains_dir = self.plan_dir / "_trains"
        if not trains_dir.exists():
            return

        for path_urn, train_file in self._iter_train_files(trains_dir):
            try:
                data = self._load_yaml_mapping(train_file)
                if not data:
                    continue

                train_urn = self._train_urn_for(data, path_urn)
                self._annotate_description(graph, train_urn, data)
                self._add_train_wagon_edges(graph, train_urn, data)
                self._add_train_step_edges(graph, train_urn, data)
            except Exception as e:
                self._logger.debug("Skipping malformed train manifest %s: %s", train_file, e)
                continue

    def _load_yaml_mapping(self, path: Path) -> Optional[dict]:
        """Parse a YAML file. None when it is empty or not a mapping."""
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else None

    @staticmethod
    def _train_urn_for(data: dict, path_urn: str) -> str:
        """A declared train identity wins; the path-derived URN is the fallback.

        The path-derived URN is already typed for a train under a subject dir.
        """
        declared = data.get("train_id") or data.get("id")
        if isinstance(declared, str) and declared.startswith("train:"):
            return declared
        return path_urn

    @staticmethod
    def _annotate_description(graph: TraceabilityGraph, urn: str, data: dict) -> None:
        """Store a manifest's description on its node metadata."""
        description = data.get("description")
        node = graph.get_node(urn)
        if node and description:
            node.metadata["description"] = description

    @staticmethod
    def _wagon_slug_in(entry) -> Optional[str]:
        """The wagon slug a dict participant/wagon entry names, if it names one."""
        if not isinstance(entry, dict):
            return None
        slug = entry.get("wagon") or entry.get("slug")
        return slug if isinstance(slug, str) and slug else None

    def _train_wagon_targets(self, data: dict) -> List[str]:
        """Deduped wagon URNs a train includes.

        Issue #285: train.schema.json requires `participants` (a list of
        wagon:* / user:* / system:* URNs) with additionalProperties:false. The
        legacy `wagons` field is kept as a deprecated read-only fallback so
        pre-1.56 plan/ trees keep building correct graphs without migration.
        Both streams merge here; user:* / system:* are dropped (they need a
        different edge type — follow-up to #285), and targets are deduped so a
        mixed-field YAML emits exactly one INCLUDES edge per wagon.
        """
        targets: List[str] = []
        seen: Set[str] = set()

        for participant in data.get("participants", []) or []:
            if isinstance(participant, str):
                if participant.startswith("wagon:"):
                    self._append_wagon_target(targets, seen, participant)
                continue

            slug = self._wagon_slug_in(participant)
            if slug:
                self._append_wagon_target(targets, seen, slug)

        for wagon_ref in data.get("wagons", []) or []:
            if isinstance(wagon_ref, str):
                self._append_wagon_target(targets, seen, wagon_ref)
                continue

            slug = self._wagon_slug_in(wagon_ref)
            if slug:
                self._append_wagon_target(targets, seen, slug)

        return targets

    @staticmethod
    def _append_wagon_target(targets: List[str], seen: Set[str], slug: str) -> None:
        """Append the wagon URN for a slug (or pass a wagon: URN through), deduped."""
        urn = slug if slug.startswith("wagon:") else f"wagon:{slug}"
        if urn not in seen:
            seen.add(urn)
            targets.append(urn)

    def _add_train_wagon_edges(
        self, graph: TraceabilityGraph, train_urn: str, data: dict
    ) -> None:
        """A train INCLUDES every wagon it lists."""
        for wagon_urn in self._train_wagon_targets(data):
            graph.add_edge(URNEdge(
                source_urn=train_urn,
                target_urn=wagon_urn,
                edge_type=EdgeType.INCLUDES,
            ))

    def _add_train_step_edges(
        self, graph: TraceabilityGraph, train_urn: str, data: dict
    ) -> None:
        """One directed wagon->wagon TRAIN_STEP edge per handoff in sequence[] (#287).

        A handoff is a sequence[] entry where ``from != to`` and both are
        ``wagon:*`` URNs. Internal-phase steps (from == to) are skipped — they
        don't advance the pipeline and would clutter journey mode. Non-wagon
        participants (user:*, system:*) are ignored: TRAIN_STEP is strictly
        wagon-to-wagon.
        """
        sequence = data.get("sequence") or []
        if not isinstance(sequence, list):
            return

        # Category is a validated FIELD on the train (#1421/#1440), never a digit
        # in its identity — a typed train:<subject>:<slug> has no digit to index.
        # A train that declares none is nominal.
        category = data.get("category")
        if not isinstance(category, str) or not category:
            category = "nominal"

        ordered_steps = sorted(
            (s for s in sequence if isinstance(s, dict)),
            key=lambda s: s.get("step", 0),
        )
        for item in ordered_steps:
            frm = item.get("from") or ""
            to = item.get("to") or ""
            if not isinstance(frm, str) or not isinstance(to, str):
                continue
            if not frm.startswith("wagon:") or not to.startswith("wagon:"):
                continue
            if frm == to:
                continue  # internal-phase step

            graph.add_edge(URNEdge(
                source_urn=frm,
                target_urn=to,
                edge_type=EdgeType.TRAIN_STEP,
                metadata={
                    "train": train_urn,
                    "step": item.get("step", 0),
                    "intent": item.get("intent", ""),
                    "category": category,
                    "source": "train-sequence",
                },
            ))

    def _build_subject_edges(self, graph: TraceabilityGraph) -> None:
        """Build subject -> train (CONTAINS) edges for typed trains (#1421).

        A typed ``train:<subject>:<slug>`` is a 2-token URN parented by its
        ``subject:<subject>`` root (grammar: ``train.parent == subject``). This
        edge makes the subject a real parent node so the typed train is not a
        topological orphan. The subject node is auto-synthesized by ``add_edge``
        if the registry has not declared it yet.

        Legacy ``train:NNNN-slug`` (a single token) has no subject parent and is
        skipped — dual-resolution keeps it resolving during the migration
        window (see ``TrainResolver``).
        """
        for urn, node in graph.nodes.items():
            if node.family != "train":
                continue
            tokens = urn[len("train:"):].split(":")
            if len(tokens) != 2 or not all(tokens):
                continue
            subject_urn = f"subject:{tokens[0]}"
            graph.add_edge(
                URNEdge(
                    source_urn=subject_urn,
                    target_urn=urn,
                    edge_type=EdgeType.CONTAINS,
                    metadata={"source": "urn-structure"},
                )
            )

    def _build_security_edges(self, graph: TraceabilityGraph) -> None:
        """
        Build security URN edges:

        - ``feature → security`` (CONTAINS) — every resolved abuse_case is
          contained by its parent feature.
        - ``security → acceptance_ref`` (REFERENCES) — every abuse_case that
          declares ``acceptance_ref`` references the named acc URN. Edges
          are emitted regardless of whether the target acc URN resolves;
          broken refs are flagged separately by ``find_broken``.
        """
        for node in list(graph.nodes.values()):
            if node.family != "security":
                continue

            # security:{wagon}:{feature}:{NNN}
            parts = node.urn.replace("security:", "").split(":")
            if len(parts) != 3:
                continue
            wagon_id, feature_id, _seq = parts
            feature_urn = f"feature:{wagon_id}:{feature_id}"

            # feature → security (CONTAINS); add_edge auto-synthesizes missing feature node
            graph.add_edge(
                URNEdge(
                    source_urn=feature_urn,
                    target_urn=node.urn,
                    edge_type=EdgeType.CONTAINS,
                    metadata={"source": "abuse-case-structure"},
                )
            )

            # security → acceptance_ref (REFERENCES). The abuse_case fields
            # were stashed onto node.metadata['declaration'] in build().
            decl_meta = node.metadata.get("declaration") or {}
            acceptance_ref = decl_meta.get("acceptance_ref")
            if not acceptance_ref or not isinstance(acceptance_ref, str):
                continue

            # If the target acc URN was not declared elsewhere, synthesize a
            # broken target node so EdgeValidator.find_broken flags it.
            if acceptance_ref not in graph.nodes:
                self._synthesize_acceptance_ref_node(graph, acceptance_ref, node)

            graph.add_edge(URNEdge(
                source_urn=node.urn,
                target_urn=acceptance_ref,
                edge_type=EdgeType.REFERENCES,
                metadata={"source": "abuse-case-acceptance-ref"},
            ))

    def _synthesize_acceptance_ref_node(
        self, graph: TraceabilityGraph, acceptance_ref: str, node: URNNode
    ) -> None:
        """Add a node for an undeclared acceptance_ref target so find_broken flags it."""
        resolution = self.registry.resolve(acceptance_ref)
        graph.add_node(URNNode(
            urn=acceptance_ref,
            family=self.registry.get_family(acceptance_ref) or "unknown",
            artifact_path=(
                resolution.resolved_paths[0] if resolution.resolved_paths else None
            ),
            metadata={
                "source_path": str(node.metadata.get("source_path", "")),
                "is_broken": resolution.is_broken,
                "resolution_error": resolution.error,
                "is_deterministic": resolution.is_deterministic,
                "is_resolved": resolution.is_resolved,
                "resolved_paths": [str(p) for p in resolution.resolved_paths],
                "synthesized_by": "abuse_case.acceptance_ref",
            },
        ))

    def _build_component_edges(self, graph: TraceabilityGraph) -> None:
        """Build feature -> component (CONTAINS) edges from component URN structure."""
        for node in list(graph.nodes.values()):
            if node.family != "component":
                continue

            # component:{wagon}:{feature}:{name}:{side}:{layer}
            parts = node.urn.replace("component:", "").split(":")
            if len(parts) < 2:
                continue

            wagon_id, feature_id = parts[0], parts[1]
            feature_urn = f"feature:{wagon_id}:{feature_id}"

            # feature -> component (CONTAINS); add_edge auto-synthesizes a missing feature
            graph.add_edge(URNEdge(
                source_urn=feature_urn,
                target_urn=node.urn,
                edge_type=EdgeType.CONTAINS,
                metadata={"source": "urn-structure"},
            ))

            # wagon -> feature fallback if feature has no wagon parent yet
            if not graph.get_parents(feature_urn, EdgeType.CONTAINS):
                graph.add_edge(URNEdge(
                    source_urn=f"wagon:{wagon_id}",
                    target_urn=feature_urn,
                    edge_type=EdgeType.CONTAINS,
                    metadata={"source": "urn-structure"},
                ))

    def _build_test_edges(
        self,
        graph: TraceabilityGraph,
        content_cache: Optional[Dict[str, str]] = None,
    ) -> None:
        """Build acc -> test (TESTED_BY) and component -> test (TESTED_BY) edges.

        Scans both legacy ``# URN: acc:...`` and V3 ``# Acceptance: acc:...`` lines.
        Component→test edges built here are derived (advisory); authoritative
        edges come from ``_build_tested_by_edges``.
        """
        # Collect components that have authoritative Tested-By edges
        components_with_tested_by = {
            edge.source_urn
            for edge in graph.edges
            if edge.edge_type == EdgeType.TESTED_BY
            and edge.metadata.get("source") == "tested-by-header"
        }

        for node in list(graph.nodes.values()):
            if node.family != "test":
                continue

            content = self._node_content(node, content_cache)
            if content is None:
                continue

            self._add_test_reference_edges(
                graph, node, content, components_with_tested_by
            )

    def _node_content(
        self, node: URNNode, content_cache: Optional[Dict[str, str]]
    ) -> Optional[str]:
        """Source of the file a node points at; None when it cannot be read."""
        # The file comes from artifact_path, else the source_path metadata
        file_path = node.artifact_path
        if not file_path:
            source_path = node.metadata.get("source_path")
            if source_path:
                file_path = Path(source_path)

        if not file_path or not Path(file_path).exists():
            return None

        cached = content_cache.get(str(file_path)) if content_cache else None
        if cached is not None:
            return cached

        try:
            return Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            self._logger.debug("Skipping unreadable file %s: %s", file_path, e)
            return None

    def _add_test_reference_edges(
        self,
        graph: TraceabilityGraph,
        node: URNNode,
        content: str,
        components_with_tested_by: Set[str],
    ) -> None:
        """TESTED_BY edges for every acc:/component: URN a test file references."""
        for line in content.split("\n"):
            # V3: # Acceptance: acc:...
            acc_match = self._ACCEPTANCE_RE.search(line)
            if acc_match:
                self._add_acc_tested_by(graph, acc_match.group(1), node)
                continue

            match = self._URN_COMMENT_RE.search(line)
            if not match:
                continue

            ref_urn = match.group(1)
            if self._REGEX_META_RE.search(ref_urn):
                continue

            # acc -> test (TESTED_BY): legacy # URN: acc:...
            if ref_urn.startswith("acc:"):
                self._add_acc_tested_by(graph, ref_urn, node)
            # component -> test (TESTED_BY): derived (advisory only). Skipped
            # when the component already has authoritative Tested-By edges.
            elif (ref_urn.startswith("component:")
                  and ref_urn in graph.nodes
                  and ref_urn not in components_with_tested_by):
                graph.add_edge(URNEdge(
                    source_urn=ref_urn,
                    target_urn=node.urn,
                    edge_type=EdgeType.TESTED_BY,
                    metadata={"source": "derived"},
                ))

    @staticmethod
    def _add_acc_tested_by(
        graph: TraceabilityGraph, ref_urn: str, node: URNNode
    ) -> None:
        """acc -> test TESTED_BY edge, when ref_urn names an acc node in the graph."""
        if ref_urn.startswith("acc:") and ref_urn in graph.nodes:
            graph.add_edge(URNEdge(
                source_urn=ref_urn,
                target_urn=node.urn,
                edge_type=EdgeType.TESTED_BY,
            ))

    def _build_tested_by_edges(
        self,
        graph: TraceabilityGraph,
        content_cache: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Build authoritative component -> test (TESTED_BY) edges from Tested-By headers.

        Scans component files for:
            # Tested-By:
            # - test:{wagon}:{feature}:{WMBT_ID}-{HARNESS}-{NNN}-{slug}
            # - test:train:{train_id}:{HARNESS}-{NNN}-{slug}

        These are authoritative — they override any derived mappings (S9.5).
        """
        for node in list(graph.nodes.values()):
            if node.family != "component":
                continue

            content = self._node_content(node, content_cache)
            if content is None:
                continue

            # Parse Tested-By test URN references. add_edge synthesizes the
            # test node when the graph has not seen it yet.
            for line in content.split("\n"):
                match = self._TESTED_BY_RE.search(line)
                if not match:
                    continue

                graph.add_edge(URNEdge(
                    source_urn=node.urn,
                    target_urn=match.group(1),
                    edge_type=EdgeType.TESTED_BY,
                    metadata={"source": "tested-by-header"},
                ))

    def _build_journey_test_edges(
        self,
        graph: TraceabilityGraph,
        content_cache: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Build train -> test (TESTED_BY) edges from Train: headers in journey tests.

        Scans test files for:
            # Train: train:{train_id}

        Links the train to the journey test.
        """
        from atdd.coach.utils.graph.resolver import TestResolver

        for node in list(graph.nodes.values()):
            if node.family != "test":
                continue

            content = self._node_content(node, content_cache)
            if content is None:
                continue

            train_ref = TestResolver.parse_test_header(content).get("train")
            if train_ref and train_ref.startswith("train:"):
                graph.add_edge(URNEdge(
                    source_urn=train_ref,
                    target_urn=node.urn,
                    edge_type=EdgeType.TESTED_BY,
                    metadata={"source": "train-header"},
                ))

    def _build_jel_contract_nodes(self, graph: TraceabilityGraph) -> None:
        """
        Discover contract schemas with urn:jel:* $id and add them as nodes.

        These nodes carry ``is_jel`` metadata so that EdgeValidator can detect
        non-ATDD contract IDs without any file I/O of its own.
        """
        contracts_dir = self.repo_root / "contracts"
        if not contracts_dir.exists():
            return

        for contract_file in contracts_dir.rglob("*.schema.json"):
            try:
                node = self._jel_contract_node(contract_file, contracts_dir)
                if node:
                    graph.add_node(node)
            except Exception as e:
                self._logger.debug(
                    "Skipping unreadable contract schema %s: %s", contract_file, e
                )
                continue

    def _jel_contract_node(
        self, contract_file: Path, contracts_dir: Path
    ) -> Optional[URNNode]:
        """Node for a urn:jel:* schema, carrying the ATDD-style ID it should have."""
        import json

        with open(contract_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        schema_id = data.get("$id", "")
        if not schema_id.startswith("urn:jel:"):
            return None

        # Derive the correct ATDD-style ID from the file path
        path_without_ext = str(contract_file.relative_to(contracts_dir)).replace(
            ".schema.json", ""
        )
        correct_id = path_without_ext.replace("/", ":").replace("\\", ":")

        return URNNode(
            urn=f"contract:{schema_id}",
            family="contract",
            artifact_path=contract_file,
            metadata={
                "is_jel": True,
                "schema_id": schema_id,
                "correct_id": correct_id,
            },
        )

    def build_from_root(
        self,
        root_urn: str,
        max_depth: int = -1,
        families: Optional[List[str]] = None,
        edge_type_exclude: Optional[Set[EdgeType]] = None,
    ) -> TraceabilityGraph:
        """
        Build a subgraph starting from a specific URN.

        Args:
            root_urn: Starting URN for the subgraph
            max_depth: Maximum traversal depth (-1 for unlimited)
            families: Optional list of families to include
            edge_type_exclude: Optional set of EdgeType values to skip during
                traversal (see TraceabilityGraph.get_subgraph). Callers use
                ``{EdgeType.TRAIN_STEP}`` to prevent structural (wagon/feature)
                roots from leaking cross-train wagons (#287).

        Returns:
            Subgraph rooted at the specified URN
        """
        full_graph = self.build(families)
        return full_graph.get_subgraph(
            root_urn, max_depth, edge_type_exclude=edge_type_exclude
        )
