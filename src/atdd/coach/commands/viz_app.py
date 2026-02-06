"""
ATDD URN Graph Visualizer
=========================
Streamlit app for interactive URN traceability graph visualization.

Launched via: atdd urn viz
Default port: 8502

Uses st-link-analysis (Cytoscape.js) for graph rendering.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st
from st_link_analysis import st_link_analysis, NodeStyle, EdgeStyle

# ---------------------------------------------------------------------------
# Bootstrap: ensure the atdd package is importable when launched via streamlit run
# ---------------------------------------------------------------------------
_src_root = str(Path(__file__).resolve().parents[3])
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)

from atdd.coach.utils.graph.graph_builder import GraphBuilder

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FAMILY_COLORS = {
    "wagon": "#4A90D9",
    "feature": "#27AE60",
    "wmbt": "#E67E22",
    "acc": "#E74C3C",
    "contract": "#8E44AD",
    "telemetry": "#16A085",
    "train": "#2C3E50",
    "component": "#D4AC0D",
    "table": "#7F8C8D",
    "migration": "#A0522D",
}

FAMILY_ICONS = {
    "wagon": "inventory_2",
    "feature": "star",
    "wmbt": "checklist",
    "acc": "verified",
    "contract": "description",
    "telemetry": "sensors",
    "train": "train",
    "component": "widgets",
    "table": "table_chart",
    "migration": "swap_horiz",
}

EDGE_STYLES_MAP = {
    "contains": "solid",
    "parent_of": "solid",
    "produces": "dashed",
    "consumes": "dashed",
    "implements": "dotted",
    "references": "dotted",
}

FALLBACK_COLOR = "#95A5A6"


def _read_env_list(key: str) -> list[str] | None:
    val = os.environ.get(key)
    if not val:
        return None
    return [v.strip() for v in val.split(",") if v.strip()]


# ---------------------------------------------------------------------------
# Graph loading
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Building URN graph...")
def load_graph(
    repo_root: str,
    root_urn: str | None,
    max_depth: int,
    families: tuple[str, ...] | None,
) -> dict:
    builder = GraphBuilder(Path(repo_root))
    family_list = list(families) if families else None

    if root_urn:
        graph = builder.build_from_root(root_urn, max_depth, family_list)
    else:
        graph = builder.build(family_list)

    return graph.to_dict()


# ---------------------------------------------------------------------------
# Cytoscape element conversion
# ---------------------------------------------------------------------------
def build_elements(
    graph_data: dict,
    search_query: str,
    selected_families: list[str],
) -> dict:
    nodes = []
    edges = []

    family_set = set(selected_families) if selected_families else None

    for node in graph_data["nodes"]:
        family = node["family"]
        if family_set and family not in family_set:
            continue

        urn = node["urn"]
        label = node.get("label") or urn.split(":")[-1]

        nodes.append({
            "data": {
                "id": urn,
                "label": family,
                "name": label,
                "urn": urn,
                "family": family,
                "path": node.get("artifact_path") or "",
            },
            "classes": "search-match" if search_query and search_query.lower() in urn.lower() else "",
        })

    node_ids = {n["data"]["id"] for n in nodes}

    for edge in graph_data["edges"]:
        src = edge["source"]
        tgt = edge["target"]
        if src not in node_ids or tgt not in node_ids:
            continue

        edge_type = edge["type"]
        edge_id = f"{src}--{edge_type}-->{tgt}"

        edges.append({
            "data": {
                "id": edge_id,
                "label": edge_type,
                "source": src,
                "target": tgt,
                "edge_type": edge_type,
            },
        })

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Style builders
# ---------------------------------------------------------------------------
def build_node_styles(families: list[str]) -> list[NodeStyle]:
    styles = []
    for family in families:
        color = FAMILY_COLORS.get(family, FALLBACK_COLOR)
        icon = FAMILY_ICONS.get(family, "circle")
        styles.append(NodeStyle(family, color, "name", icon))
    return styles


def build_edge_styles(edge_types: list[str]) -> list[EdgeStyle]:
    styles = []
    seen = set()
    for etype in edge_types:
        if etype in seen:
            continue
        seen.add(etype)
        styles.append(EdgeStyle(etype, caption="label", directed=True))
    return styles


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(
        page_title="ATDD URN Graph",
        page_icon="🔗",
        layout="wide",
    )

    # --- Read launch parameters from environment ---
    repo_root = os.environ.get("ATDD_VIZ_REPO", os.getcwd())
    env_root_urn = os.environ.get("ATDD_VIZ_ROOT")
    env_depth = int(os.environ.get("ATDD_VIZ_DEPTH", "-1"))
    env_families = _read_env_list("ATDD_VIZ_FAMILIES")

    st.title("ATDD URN Traceability Graph")

    # --- Sidebar controls ---
    with st.sidebar:
        st.header("Controls")

        root_urn = st.text_input(
            "Root URN (subgraph)",
            value=env_root_urn or "",
            placeholder="e.g. wagon:my-wagon",
        )
        root_urn = root_urn.strip() or None

        depth = st.number_input(
            "Depth (-1 = unlimited)",
            min_value=-1,
            value=env_depth,
            step=1,
        )

        # Load graph to discover available families
        graph_data = load_graph(
            repo_root,
            root_urn,
            depth,
            tuple(env_families) if env_families else None,
        )

        available_families = sorted(
            graph_data.get("metadata", {}).get("families", [])
        )

        selected_families = st.multiselect(
            "Family filter",
            options=available_families,
            default=available_families,
        )

        st.divider()

        search_query = st.text_input(
            "Search URN",
            placeholder="substring match",
        )

        st.divider()

        # Export
        json_str = json.dumps(graph_data, indent=2, default=str)
        st.download_button(
            label="Export JSON",
            data=json_str,
            file_name="urn_graph.json",
            mime="application/json",
        )

        st.caption(
            f"Nodes: {graph_data['metadata']['node_count']} | "
            f"Edges: {graph_data['metadata']['edge_count']}"
        )

    # --- Build Cytoscape elements ---
    elements = build_elements(graph_data, search_query, selected_families)

    if not elements["nodes"]:
        st.warning("No URN nodes found. Check your repository or filters.")
        return

    # Collect all families and edge types present in the filtered set
    present_families = sorted({n["data"]["family"] for n in elements["nodes"]})
    present_edge_types = [e["data"]["edge_type"] for e in elements["edges"]]

    node_styles = build_node_styles(present_families)
    edge_styles = build_edge_styles(present_edge_types)

    # --- Render graph ---
    st_link_analysis(
        elements,
        layout="cose",
        node_styles=node_styles,
        edge_styles=edge_styles,
        key="urn_graph",
    )

    # --- Search results summary ---
    if search_query:
        matches = [
            n["data"]["urn"]
            for n in elements["nodes"]
            if search_query.lower() in n["data"]["urn"].lower()
        ]
        if matches:
            st.success(f"Found {len(matches)} match(es) for '{search_query}'")
            with st.expander("Matching URNs"):
                for m in matches:
                    st.code(m)
        else:
            st.info(f"No URNs matching '{search_query}'")


if __name__ == "__main__":
    main()
