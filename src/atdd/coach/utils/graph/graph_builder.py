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

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.graph.resolver import (
    ResolverRegistry,
    URNDeclaration,
    URNResolution,
)


class EdgeType(Enum):
    """Types of edges in the traceability graph."""

    CONTAINS = "contains"  # Parent-child containment (wagon contains feature)
    PRODUCES = "produces"  # Producer relationship (wagon produces contract)
    CONSUMES = "consumes"  # Consumer relationship (wagon consumes contract)
    IMPLEMENTS = "implements"  # Implementation relationship (component implements feature)
    REFERENCES = "references"  # General reference relationship
    INCLUDES = "includes"  # Train includes wagons (many-to-many)
    TESTED_BY = "tested_by"  # Verification relationship (acc/component tested by test)


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


class TraceabilityGraph:
    """
    The complete traceability graph with nodes and edges.

    Provides methods for:
    - Adding/removing nodes and edges
    - Querying graph structure
    - Exporting to JSON and DOT formats
    """

    def __init__(self, allowed_families: Optional[List[str]] = None):
        self._nodes: Dict[str, URNNode] = {}
        self._edges: List[URNEdge] = []
        self._edges_by_source: Dict[str, List[URNEdge]] = {}
        self._edges_by_target: Dict[str, List[URNEdge]] = {}
        self._allowed_families: Optional[Set[str]] = set(allowed_families) if allowed_families else None

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
        if self._allowed_families:
            if source_family not in self._allowed_families:
                return False
            if target_family not in self._allowed_families:
                return False

        # Ensure source and target nodes exist
        if edge.source_urn not in self._nodes:
            self._nodes[edge.source_urn] = URNNode(
                urn=edge.source_urn, family=source_family
            )
        if edge.target_urn not in self._nodes:
            self._nodes[edge.target_urn] = URNNode(
                urn=edge.target_urn, family=target_family
            )

        self._edges.append(edge)

        # Index by source
        if edge.source_urn not in self._edges_by_source:
            self._edges_by_source[edge.source_urn] = []
        self._edges_by_source[edge.source_urn].append(edge)

        # Index by target
        if edge.target_urn not in self._edges_by_target:
            self._edges_by_target[edge.target_urn] = []
        self._edges_by_target[edge.target_urn].append(edge)

        return True

    def _infer_family(self, urn: str) -> str:
        """Infer family from URN prefix."""
        if ":" in urn:
            return urn.split(":")[0]
        return "unknown"

    def get_node(self, urn: str) -> Optional[URNNode]:
        """Get a node by URN."""
        return self._nodes.get(urn)

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

    def get_subgraph(self, root_urn: str, max_depth: int = -1) -> "TraceabilityGraph":
        """
        Extract a subgraph starting from a root node.

        Args:
            root_urn: Starting node URN
            max_depth: Maximum traversal depth (-1 for unlimited)

        Returns:
            New graph containing only reachable nodes and edges
        """
        subgraph = TraceabilityGraph()
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(root_urn, 0)]

        while queue:
            urn, depth = queue.pop(0)
            if urn in visited:
                continue
            if max_depth >= 0 and depth > max_depth:
                continue

            visited.add(urn)

            node = self.get_node(urn)
            if node:
                subgraph.add_node(node)

            for edge in self.get_outgoing_edges(urn):
                subgraph.add_edge(edge)
                if edge.target_urn not in visited:
                    queue.append((edge.target_urn, depth + 1))

        return subgraph

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

        # Define node colors by family
        family_colors = {
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

        # Add nodes
        for urn, node in self._nodes.items():
            color = family_colors.get(node.family, "#FAFAFA")
            safe_urn = urn.replace('"', '\\"')
            safe_label = node.display_label.replace('"', '\\"')
            lines.append(
                f'    "{safe_urn}" [label="{safe_label}\\n({node.family})", fillcolor="{color}"];'
            )

        lines.append("")

        # Define edge styles by type
        edge_styles = {
            EdgeType.CONTAINS: 'style=solid, color="#2196F3"',
            EdgeType.PRODUCES: 'style=dashed, color="#4CAF50"',
            EdgeType.CONSUMES: 'style=dashed, color="#FF9800"',
            EdgeType.IMPLEMENTS: 'style=dotted, color="#9C27B0"',
            EdgeType.REFERENCES: 'style=dotted, color="#607D8B"',
            EdgeType.INCLUDES: 'style=bold, color="#F44336"',
            EdgeType.TESTED_BY: 'style=dashed, color="#E91E63"',
        }

        # Add edges
        for edge in self._edges:
            style = edge_styles.get(edge.edge_type, "")
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

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or find_repo_root()
        self.registry = ResolverRegistry(self.repo_root)
        self.plan_dir = self.repo_root / "plan"

    def build(self, families: Optional[List[str]] = None) -> TraceabilityGraph:
        """
        Build the complete traceability graph.

        Args:
            families: Optional list of families to include. If None, includes all.

        Returns:
            Complete traceability graph
        """
        graph = TraceabilityGraph(allowed_families=families)

        # 1. Add all declared URNs as nodes
        declarations = self.registry.find_all_declarations(families)
        for family, decls in declarations.items():
            for decl in decls:
                resolution = self.registry.resolve(decl.urn)
                artifact_path = (
                    resolution.resolved_paths[0] if resolution.resolved_paths else None
                )
                node = URNNode(
                    urn=decl.urn,
                    family=family,
                    artifact_path=artifact_path,
                    metadata={"source_path": str(decl.source_path)},
                )
                graph.add_node(node)

        # 2. Build edges from manifest relationships
        self._build_containment_edges(graph)
        self._build_produce_consume_edges(graph)
        self._build_train_edges(graph)
        self._build_component_edges(graph)
        self._build_test_edges(graph)
        self._build_tested_by_edges(graph)
        self._build_journey_test_edges(graph)

        return graph

    def _build_containment_edges(self, graph: TraceabilityGraph) -> None:
        """Build containment edges (wagon -> feature -> wmbt -> acceptance)."""
        import yaml

        if not self.plan_dir.exists():
            return

        # Wagon contains features
        for feature_decl in graph.nodes.values():
            if feature_decl.family != "feature":
                continue

            # Parse wagon from feature URN: feature:wagon:feature-name
            parts = feature_decl.urn.replace("feature:", "").split(":")
            if len(parts) >= 2:
                wagon_urn = f"wagon:{parts[0]}"
                if wagon_urn in graph.nodes:
                    graph.add_edge(
                        URNEdge(
                            source_urn=wagon_urn,
                            target_urn=feature_decl.urn,
                            edge_type=EdgeType.CONTAINS,
                        )
                    )

        # Wagon contains WMBTs
        for wmbt_decl in graph.nodes.values():
            if wmbt_decl.family != "wmbt":
                continue

            # Parse wagon from WMBT URN: wmbt:wagon:STEP001
            parts = wmbt_decl.urn.replace("wmbt:", "").split(":")
            if len(parts) >= 2:
                wagon_urn = f"wagon:{parts[0]}"
                if wagon_urn in graph.nodes:
                    graph.add_edge(
                        URNEdge(
                            source_urn=wagon_urn,
                            target_urn=wmbt_decl.urn,
                            edge_type=EdgeType.CONTAINS,
                        )
                    )

        # WMBT contains acceptances
        for acc_decl in graph.nodes.values():
            if acc_decl.family != "acc":
                continue

            # Parse wagon and wmbt from acc URN: acc:wagon:WMBT-HARNESS-SEQ
            parts = acc_decl.urn.replace("acc:", "").split(":")
            if len(parts) >= 2:
                wagon_id = parts[0]
                facets = parts[1].split("-")
                if len(facets) >= 1:
                    wmbt_id = facets[0]
                    wmbt_urn = f"wmbt:{wagon_id}:{wmbt_id}"
                    if wmbt_urn in graph.nodes:
                        graph.add_edge(
                            URNEdge(
                                source_urn=wmbt_urn,
                                target_urn=acc_decl.urn,
                                edge_type=EdgeType.CONTAINS,
                            )
                        )

    def _resolve_contract_ref(self, contract_ref: str) -> Optional[str]:
        """
        Resolve a contract reference to a URN.

        Handles:
        - URN format (contract:theme:domain...) - returned as-is
        - File path (contracts/...) - reads $id from schema
        - Schema ID (theme:domain...) - prefixed with contract:
        """
        import json

        if not contract_ref:
            return None

        # Already a contract URN
        if contract_ref.startswith("contract:"):
            return contract_ref

        # File path - resolve via $id
        if contract_ref.startswith("contracts/") or contract_ref.endswith(".schema.json"):
            contract_path = self.repo_root / contract_ref
            if contract_path.exists():
                try:
                    with open(contract_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    schema_id = data.get("$id")
                    # Skip urn:jel:* IDs
                    if schema_id and not schema_id.startswith("urn:jel:"):
                        return f"contract:{schema_id}"
                except Exception:
                    pass
            return None

        # Schema ID - prefix with contract:
        return f"contract:{contract_ref}"

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
        import yaml

        if not self.plan_dir.exists():
            return

        for manifest_path in self.plan_dir.rglob("_*.yaml"):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if not data or not isinstance(data, dict):
                    continue

                wagon_slug = data.get("wagon")
                if not wagon_slug:
                    continue

                wagon_urn = f"wagon:{wagon_slug}"

                # Process produce items
                for produce in data.get("produce", []):
                    contract_ref = produce.get("contract")
                    telemetry_ref = produce.get("telemetry")
                    produce_urn = produce.get("urn")

                    # Use explicit URN if provided, otherwise resolve contract ref
                    if produce_urn and produce_urn.startswith("contract:"):
                        contract_urn = produce_urn
                    else:
                        contract_urn = self._resolve_contract_ref(contract_ref)

                    # Wagon produces contract
                    if contract_urn:
                        graph.add_edge(
                            URNEdge(
                                source_urn=wagon_urn,
                                target_urn=contract_urn,
                                edge_type=EdgeType.PRODUCES,
                            )
                        )

                    # Wagon produces telemetry
                    if telemetry_ref:
                        refs = telemetry_ref if isinstance(telemetry_ref, list) else [telemetry_ref]
                        for ref in refs:
                            telemetry_urn = self._resolve_telemetry_ref(ref)
                            if telemetry_urn:
                                graph.add_edge(
                                    URNEdge(
                                        source_urn=wagon_urn,
                                        target_urn=telemetry_urn,
                                        edge_type=EdgeType.PRODUCES,
                                    )
                                )

                # Process consume items
                for consume in data.get("consume", []):
                    contract_ref = consume.get("contract")
                    telemetry_ref = consume.get("telemetry")

                    # Wagon consumes contract
                    contract_urn = self._resolve_contract_ref(contract_ref)
                    if contract_urn:
                        graph.add_edge(
                            URNEdge(
                                source_urn=wagon_urn,
                                target_urn=contract_urn,
                                edge_type=EdgeType.CONSUMES,
                            )
                        )

                    # Wagon consumes telemetry
                    if telemetry_ref:
                        refs = telemetry_ref if isinstance(telemetry_ref, list) else [telemetry_ref]
                        for ref in refs:
                            telemetry_urn = self._resolve_telemetry_ref(ref)
                            if telemetry_urn:
                                graph.add_edge(
                                    URNEdge(
                                        source_urn=wagon_urn,
                                        target_urn=telemetry_urn,
                                        edge_type=EdgeType.CONSUMES,
                                    )
                                )

            except Exception:
                continue

    def _build_train_edges(self, graph: TraceabilityGraph) -> None:
        """Build train -> wagon containment edges."""
        import yaml

        trains_dir = self.plan_dir / "_trains"
        if not trains_dir.exists():
            return

        for train_file in trains_dir.glob("*.yaml"):
            try:
                with open(train_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if not data or not isinstance(data, dict):
                    continue

                train_id = data.get("id") or train_file.stem
                train_urn = f"train:{train_id}"

                # Train contains wagons
                for wagon_ref in data.get("wagons", []):
                    if isinstance(wagon_ref, str):
                        wagon_urn = (
                            wagon_ref
                            if wagon_ref.startswith("wagon:")
                            else f"wagon:{wagon_ref}"
                        )
                        graph.add_edge(
                            URNEdge(
                                source_urn=train_urn,
                                target_urn=wagon_urn,
                                edge_type=EdgeType.INCLUDES,
                            )
                        )
                    elif isinstance(wagon_ref, dict):
                        wagon_slug = wagon_ref.get("wagon") or wagon_ref.get("slug")
                        if wagon_slug:
                            wagon_urn = (
                                wagon_slug
                                if wagon_slug.startswith("wagon:")
                                else f"wagon:{wagon_slug}"
                            )
                            graph.add_edge(
                                URNEdge(
                                    source_urn=train_urn,
                                    target_urn=wagon_urn,
                                    edge_type=EdgeType.INCLUDES,
                                )
                            )

            except Exception:
                continue

    def _build_component_edges(self, graph: TraceabilityGraph) -> None:
        """Build feature -> component (CONTAINS) edges from component URN structure."""
        for node in list(graph.nodes.values()):
            if node.family != "component":
                continue

            # component:{wagon}:{feature}:{name}:{side}:{layer}
            parts = node.urn.replace("component:", "").split(":")
            if len(parts) >= 2:
                wagon_id, feature_id = parts[0], parts[1]
                feature_urn = f"feature:{wagon_id}:{feature_id}"
                if feature_urn in graph.nodes:
                    graph.add_edge(
                        URNEdge(
                            source_urn=feature_urn,
                            target_urn=node.urn,
                            edge_type=EdgeType.CONTAINS,
                        )
                    )

    def _build_test_edges(self, graph: TraceabilityGraph) -> None:
        """Build acc -> test (TESTED_BY) and component -> test (TESTED_BY) edges."""
        import re

        urn_comment_re = re.compile(r"(?:#|//)\s*[Uu][Rr][Nn]:\s*([^\s]+)")
        regex_meta_re = re.compile(r"[\[\]\(\)\*\+\?\{\}\^\$\\]")

        for node in list(graph.nodes.values()):
            if node.family != "test":
                continue

            # Find the test file from artifact_path or source_path metadata
            test_path = node.artifact_path
            if not test_path:
                source_path = node.metadata.get("source_path")
                if source_path:
                    test_path = Path(source_path)

            if not test_path or not Path(test_path).exists():
                continue

            try:
                content = Path(test_path).read_text(encoding="utf-8")
            except Exception:
                continue

            for line in content.split("\n"):
                match = urn_comment_re.search(line)
                if not match:
                    continue
                ref_urn = match.group(1)
                if regex_meta_re.search(ref_urn):
                    continue

                # acc -> test (TESTED_BY): acceptance criterion is tested by this test
                if ref_urn.startswith("acc:") and ref_urn in graph.nodes:
                    graph.add_edge(
                        URNEdge(
                            source_urn=ref_urn,
                            target_urn=node.urn,
                            edge_type=EdgeType.TESTED_BY,
                        )
                    )
                # component -> test (TESTED_BY): component is tested by this test
                elif ref_urn.startswith("component:") and ref_urn in graph.nodes:
                    graph.add_edge(
                        URNEdge(
                            source_urn=ref_urn,
                            target_urn=node.urn,
                            edge_type=EdgeType.TESTED_BY,
                        )
                    )

    def _build_tested_by_edges(self, graph: TraceabilityGraph) -> None:
        """
        Build authoritative component -> test (TESTED_BY) edges from Tested-By headers.

        Scans component files for:
            # Tested-By:
            # - test:{wagon}:{feature}:{WMBT_ID}-{HARNESS}-{NNN}-{slug}
            # - test:train:{train_id}:{HARNESS}-{NNN}-{slug}

        These are authoritative — they override any derived mappings (S9.5).
        """
        import re

        tested_by_re = re.compile(r"(?:#|//)\s*-\s*(test:[^\s]+)")

        for node in list(graph.nodes.values()):
            if node.family != "component":
                continue

            # Find the component source file
            comp_path = node.artifact_path
            if not comp_path:
                source_path = node.metadata.get("source_path")
                if source_path:
                    comp_path = Path(source_path)

            if not comp_path or not Path(comp_path).exists():
                continue

            try:
                content = Path(comp_path).read_text(encoding="utf-8")
            except Exception:
                continue

            # Parse Tested-By test URN references
            for line in content.split("\n"):
                match = tested_by_re.search(line)
                if not match:
                    continue
                test_urn = match.group(1)

                # Ensure the test node exists in graph (create if needed)
                graph.add_edge(
                    URNEdge(
                        source_urn=node.urn,
                        target_urn=test_urn,
                        edge_type=EdgeType.TESTED_BY,
                        metadata={"source": "tested-by-header"},
                    )
                )

    def _build_journey_test_edges(self, graph: TraceabilityGraph) -> None:
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

            test_path = node.artifact_path
            if not test_path:
                source_path = node.metadata.get("source_path")
                if source_path:
                    test_path = Path(source_path)

            if not test_path or not Path(test_path).exists():
                continue

            try:
                content = Path(test_path).read_text(encoding="utf-8")
            except Exception:
                continue

            header = TestResolver.parse_test_header(content)
            train_ref = header.get("train")
            if train_ref and train_ref.startswith("train:"):
                graph.add_edge(
                    URNEdge(
                        source_urn=train_ref,
                        target_urn=node.urn,
                        edge_type=EdgeType.TESTED_BY,
                        metadata={"source": "train-header"},
                    )
                )

    def build_from_root(
        self, root_urn: str, max_depth: int = -1, families: Optional[List[str]] = None
    ) -> TraceabilityGraph:
        """
        Build a subgraph starting from a specific URN.

        Args:
            root_urn: Starting URN for the subgraph
            max_depth: Maximum traversal depth (-1 for unlimited)
            families: Optional list of families to include

        Returns:
            Subgraph rooted at the specified URN
        """
        full_graph = self.build(families)
        return full_graph.get_subgraph(root_urn, max_depth)
