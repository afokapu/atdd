"""
ATDD URN Graph Visualizer
=========================
Streamlit app for interactive URN traceability graph visualization.

Launched via: atdd repo viz
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
# FAMILY_COLORS / FAMILY_ICONS are intentionally closed enumerations:
# visualization-only mappings with FALLBACK_COLOR / "circle" defaults for
# unknown families. New URN families render with the fallback styles and
# need no edits here. Audit reference: docs/urn-prefix-audit-2026.md (#3).
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
    "contains":    {"color": "#2C3E50", "line_style": "solid"},
    "includes":    {"color": "#4A90D9", "line_style": "solid"},
    "produces":    {"color": "#8E44AD", "line_style": "dashed"},
    "consumes":    {"color": "#8E44AD", "line_style": "dashed"},
    "implements":  {"color": "#27AE60", "line_style": "dotted"},
    "references":  {"color": "#95A5A6", "line_style": "dotted"},
    "tested_by":   {"color": "#E91E63", "line_style": "dashed"},
    # Journey-mode edge: one per handoff inside a train's sequence[].
    # Color resolved per-edge from metadata.category at render time so each
    # train's pipeline is legible at a glance (nominal vs alternate vs error).
    "train_step":  {"color": "#F39C12", "line_style": "solid"},
}

# Color per train category digit (second character of train_id).
# See train.convention.yaml and issue #287 Conceptual Model.
TRAIN_CATEGORY_COLORS = {
    "nominal":   "#4A90D9",  # 0 — blue
    "error":     "#E74C3C",  # 1 — red
    "alternate": "#F39C12",  # 2 — orange
    "exception": "#9B59B6",  # 3 — purple
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
    exclude_train_step: bool,
) -> dict:
    """
    Build the graph for a given view.

    Args:
        exclude_train_step: If True, drop TRAIN_STEP edges from the returned
            dict. Structural mode passes True so wagon/feature subgraphs don't
            leak cross-train wagons via handoffs (#287). Journey mode passes
            False so the handoff arrows render.
    """
    builder = GraphBuilder(Path(repo_root))
    family_list = list(families) if families else None
    exclude = {EdgeType.TRAIN_STEP} if exclude_train_step else None

    if root_urn:
        graph = builder.build_from_root(
            root_urn, max_depth, family_list, edge_type_exclude=exclude
        )
    else:
        graph = builder.build(family_list)

    data = graph.to_dict()
    if exclude and not root_urn:
        data["edges"] = [
            e for e in data["edges"] if e["type"] != EdgeType.TRAIN_STEP.value
        ]
    return data


def list_trains(graph_data: dict) -> list[dict]:
    """
    Extract train nodes from a full graph, sorted by URN. Each entry carries
    the URN, label/title, and (if present) a best-effort category inferred
    from the train_id pattern ``{theme}{category}{variation}``.
    """
    trains = []
    for node in graph_data.get("nodes", []):
        if node.get("family") != "train":
            continue
        urn = node["urn"]
        local = urn.split(":", 1)[-1]
        category_digit = local[1:2] if len(local) >= 2 and local[:4].isdigit() else None
        category_name = {
            "0": "nominal",
            "1": "error",
            "2": "alternate",
            "3": "exception",
        }.get(category_digit)
        trains.append({
            "urn": urn,
            "label": node.get("label") or local,
            "category": category_name,
        })
    trains.sort(key=lambda t: t["urn"])
    return trains


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
        metadata = edge.get("metadata") or {}
        caption = _edge_caption(edge_type, metadata)
        edge_id = f"{src}--{edge_type}-->{tgt}"

        edges.append({
            "data": {
                "id": edge_id,
                "label": edge_type,
                "source": src,
                "target": tgt,
                "edge_type": edge_type,
                "caption": caption,
            },
        })

    return {"nodes": nodes, "edges": edges}


def _edge_caption(edge_type: str, metadata: dict) -> str:
    """Return the per-edge display caption."""
    if edge_type == "train_step":
        step = metadata.get("step")
        intent = (metadata.get("intent") or "").strip()
        snippet = intent if len(intent) <= 40 else intent[:37] + "..."
        if step is not None and snippet:
            return f"step {step} — {snippet}"
        if step is not None:
            return f"step {step}"
        return "train_step"
    return edge_type


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
    """Build EdgeStyle instances, pulling colors from EDGE_STYLES_MAP."""
    styles = []
    seen = set()
    for etype in edge_types:
        if etype in seen:
            continue
        seen.add(etype)
        cfg = EDGE_STYLES_MAP.get(etype, {})
        color = cfg.get("color", FALLBACK_COLOR)
        styles.append(
            EdgeStyle(etype, color=color, caption="caption", directed=True)
        )
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

        mode = st.radio(
            "Mode",
            options=["Structural", "Journey"],
            index=0,
            help=(
                "Structural hides TRAIN_STEP edges so the graph reflects "
                "containment/production relationships. Journey picks one "
                "train and renders its ordered pipeline via TRAIN_STEP "
                "handoffs (#287)."
            ),
        )

        # Train list is a function of the full graph; load once with
        # TRAIN_STEP included so we can enumerate trains regardless of mode.
        _full_graph = load_graph(
            repo_root,
            None,
            env_depth,
            tuple(env_families) if env_families else None,
            exclude_train_step=False,
        )
        trains = list_trains(_full_graph)

        if mode == "Journey":
            if not trains:
                st.warning("No trains found in this repository.")
                return

            train_labels = {
                t["urn"]: (
                    f"{t['label']} [{t['category']}]" if t["category"]
                    else t["label"]
                )
                for t in trains
            }
            default_urn = env_root_urn if env_root_urn in train_labels else trains[0]["urn"]
            default_index = list(train_labels.keys()).index(default_urn)
            train_urn = st.selectbox(
                "Train",
                options=list(train_labels.keys()),
                index=default_index,
                format_func=lambda u: train_labels[u],
            )
            root_urn = train_urn
            depth = -1
            exclude_train_step = False
        else:
            root_urn = st.text_input(
                "Root URN (subgraph)",
                value=env_root_urn or "",
                placeholder="e.g. wagon:my-wagon",
            ).strip() or None
            depth = st.number_input(
                "Depth (-1 = unlimited)",
                min_value=-1,
                value=env_depth,
                step=1,
            )
            exclude_train_step = True

        graph_data = load_graph(
            repo_root,
            root_urn,
            depth,
            tuple(env_families) if env_families else None,
            exclude_train_step=exclude_train_step,
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
            f"Mode: {mode} | "
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
