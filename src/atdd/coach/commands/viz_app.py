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

from atdd.coach.utils.graph.graph_builder import EdgeType, GraphBuilder

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
    "test": "#E91E63",
}

FAMILY_ICONS = {
    "wagon": "tram",
    "feature": "star",
    "wmbt": "checklist",
    "acc": "verified",
    "contract": "description",
    "telemetry": "sensors",
    "train": "train",
    "component": "code",
    "table": "table_chart",
    "migration": "swap_horiz",
    "test": "science",
}

EDGE_STYLES_MAP = {
    "contains": "solid",
    "includes": "solid",
    "produces": "dashed",
    "consumes": "dashed",
    "implements": "dotted",
    "references": "dotted",
    "tested_by": "dashed",
    # #287: ordered wagon→wagon handoff inside a train's sequence[].
    # Rendered as a solid directed arrow in Journey mode; suppressed
    # from Structural mode via edge_type_exclude.
    "train_step": "solid",
}

# #287: edge types that Structural mode hides by default. Journey mode
# clears this filter so TRAIN_STEP handoffs are visible.
STRUCTURAL_MODE_EDGE_EXCLUDE: frozenset[EdgeType] = frozenset({EdgeType.TRAIN_STEP})

# Category → color for TRAIN_STEP edge labels in Journey mode.
# Matches the train_id naming convention {theme}{category}{variation}:
# 0=nominal, 1=error, 2=alternate, 3=exception.
TRAIN_CATEGORY_COLORS = {
    "nominal":   "#27AE60",
    "error":     "#E74C3C",
    "alternate": "#E67E22",
    "exception": "#8E44AD",
}

TRAIN_CATEGORY_BADGES = {
    "nominal":   "🟢",
    "error":     "🔴",
    "alternate": "🟡",
    "exception": "🟣",
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
    exclude_edge_types: tuple[str, ...] = (),
) -> dict:
    """
    Build and serialize the URN traceability graph.

    Args:
        repo_root: Absolute path to the repo root.
        root_urn: Optional URN to root a subgraph at.
        max_depth: Traversal depth (-1 = unlimited).
        families: Optional tuple of families to include.
        exclude_edge_types: Tuple of edge-type string values to drop from
            the subgraph (e.g. ``("train_step",)`` for Structural mode).
            Applied only when ``root_urn`` is set — a full-graph build
            always returns every edge. The argument is a tuple of strings
            (not a set of EdgeType) so Streamlit's cache can hash it.
    """
    builder = GraphBuilder(Path(repo_root))
    family_list = list(families) if families else None

    exclude: set[EdgeType] | None = None
    if exclude_edge_types:
        exclude = {EdgeType(v) for v in exclude_edge_types}

    if root_urn:
        graph = builder.build_from_root(
            root_urn, max_depth, family_list, edge_type_exclude=exclude
        )
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

        # #287: view mode toggle. Structural is today's behavior and stays
        # the default — journey mode is opt-in.
        mode = st.radio(
            "View mode",
            options=["Structural", "Journey"],
            index=0,
            horizontal=True,
            help=(
                "Structural: full URN graph minus per-train handoffs. "
                "Journey: one chosen train rendered as an ordered pipeline."
            ),
        )

        if mode == "Journey":
            # Discover trains from the full graph (no root, no exclude) so
            # the dropdown is populated even before a selection is made.
            _journey_discovery = load_graph(
                repo_root,
                None,
                env_depth,
                tuple(env_families) if env_families else None,
                (),
            )
            train_nodes = [
                n for n in _journey_discovery.get("nodes", [])
                if n.get("family") == "train"
            ]

            if not train_nodes:
                st.warning(
                    "Journey mode needs at least one `train:*` node in the graph. "
                    "No trains were discovered — falling back to Structural."
                )
                mode = "Structural"
                selected_train_urn = None
            else:
                # Build dropdown entries as "{badge} {train_id} — {title}"
                # so the user can scan by scenario category (🟢 🔴 🟡 🟣).
                def _train_entry_label(node: dict) -> str:
                    urn = node["urn"]
                    train_id = urn.split(":", 1)[1] if ":" in urn else urn
                    category_digit = train_id[1] if len(train_id) > 1 else "0"
                    category = {
                        "0": "nominal",
                        "1": "error",
                        "2": "alternate",
                        "3": "exception",
                    }.get(category_digit, "nominal")
                    badge = TRAIN_CATEGORY_BADGES.get(category, "⚪")
                    title = (node.get("label") or "").strip() or train_id
                    return f"{badge} {train_id} — {title}"

                train_options = sorted(train_nodes, key=lambda n: n["urn"])
                labels = [_train_entry_label(n) for n in train_options]
                urn_by_label = {lbl: tn["urn"] for lbl, tn in zip(labels, train_options)}

                selected_label = st.selectbox(
                    "Train",
                    options=labels,
                    index=0,
                    help="Choose a train to render its wagon pipeline.",
                )
                selected_train_urn = urn_by_label[selected_label]

            root_urn = selected_train_urn
            depth = -1
            st.caption(
                f"Journey mode — rooted at `{selected_train_urn}` (depth = unlimited)."
                if selected_train_urn
                else "Journey mode — waiting for a train selection."
            )
        else:
            selected_train_urn = None
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

        # Load the graph. Structural mode hides TRAIN_STEP via the exclude
        # tuple; Journey mode passes no exclude so handoffs are rendered.
        if mode == "Structural":
            exclude_edges = tuple(et.value for et in STRUCTURAL_MODE_EDGE_EXCLUDE)
        else:
            exclude_edges = ()

        graph_data = load_graph(
            repo_root,
            root_urn,
            depth,
            tuple(env_families) if env_families else None,
            exclude_edges,
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
