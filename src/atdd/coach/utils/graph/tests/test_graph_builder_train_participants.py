# URN: test:coach:graph_builder:train_participants
"""
Regression test for issue #285: train→wagon INCLUDES edges must be built from
the schema-canonical `participants` field on train YAMLs.

Root cause of #285: train.schema.json requires `participants` (with
`additionalProperties: false`) while graph_builder._build_train_edges was
reading the legacy `wagons` field. Any schema-valid plan/ tree therefore
produced a URN graph with zero train→wagon edges, silently breaking
`atdd urn graph`, `atdd urn viz`, and every downstream DOT/SVG/PNG render.

These tests pin the contract so the drift cannot silently return:

- `participants: ["wagon:x"]` must yield ≥1 train→wagon INCLUDES edge.
- Legacy `wagons: ["x"]` must still work (backward compatibility).
- Mixed `participants` + `wagons` must NOT emit duplicate edges.
- Non-wagon participants (`user:*`, `system:*`) must NOT produce phantom
  `wagon:user` / `wagon:system` edges — `INCLUDES` is strictly train→wagon.

Naming follows filename.convention.yaml: test_{component}_{what}.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from atdd.coach.utils.graph.graph_builder import (
    EdgeType,
    GraphBuilder,
    TraceabilityGraph,
    URNEdge,
    URNNode,
)

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_minimal_wagon(plan_dir: Path, slug: str) -> Path:
    """Create a minimal wagon YAML so the builder has a wagon node to link to."""
    wagon_dir = plan_dir / slug.replace("-", "_")
    wagon_dir.mkdir(parents=True, exist_ok=True)
    wagon_file = wagon_dir / f"_{slug.replace('-', '_')}.yaml"
    wagon_file.write_text(
        "\n".join(
            [
                f"wagon: {slug}",
                f"urn: wagon:{slug}",
                'description: "Minimal wagon for participants regression test"',
                "theme: commons",
                'subject: "test:worker"',
                'context: "test"',
                'action: "does a thing"',
                'goal: "achieves the thing"',
                'outcome: "thing achieved"',
                "produce: []",
                "consume: []",
                "wmbt:",
                "  total: 0",
                "",
            ]
        )
    )
    return wagon_file


def _write_train(plan_dir: Path, train_id: str, body: str) -> Path:
    trains_dir = plan_dir / "_trains"
    trains_dir.mkdir(parents=True, exist_ok=True)
    train_file = trains_dir / f"{train_id}.yaml"
    train_file.write_text(body)
    return train_file


def _count_train_wagon_edges(graph: TraceabilityGraph) -> int:
    return sum(
        1
        for e in graph.edges
        if e.edge_type == EdgeType.INCLUDES
        and e.source_urn.startswith("train:")
        and e.target_urn.startswith("wagon:")
    )


def _build_graph(repo_root: Path) -> TraceabilityGraph:
    """Build a graph with cache disabled and URN-less code scan skipped."""
    builder = GraphBuilder(repo_root=repo_root, use_cache=False)
    graph = TraceabilityGraph()
    # Seed the wagon node so add_edge does not need to synthesize family.
    # (GraphBuilder.add_edge auto-synthesizes missing nodes from family prefix.)
    builder._build_train_edges(graph)
    return graph


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_participants_field_produces_train_to_wagon_includes_edge(tmp_path):
    """
    GIVEN a schema-canonical train YAML with `participants: ["wagon:x"]` only
    WHEN _build_train_edges runs
    THEN at least one `train:... → wagon:x INCLUDES` edge must exist.

    This is the primary regression gate for issue #285.
    """
    repo_root = tmp_path
    plan = repo_root / "plan"
    plan.mkdir()
    _write_minimal_wagon(plan, "aggregate-bank-data")
    _write_train(
        plan,
        "0001-connect-nominal",
        "\n".join(
            [
                'train_id: "0001-connect-nominal"',
                'title: "Connect nominal"',
                'description: "Minimal train for regression test"',
                "themes: [commons]",
                "primary_wagon: aggregate-bank-data",
                "participants:",
                '  - "wagon:aggregate-bank-data"',
                "sequence:",
                "  - step: 1",
                '    intent: "Traverse"',
                '    from: "wagon:aggregate-bank-data"',
                '    to: "wagon:aggregate-bank-data"',
                '    artifact: "aggregation:scenario-step"',
                "",
            ]
        ),
    )

    graph = _build_graph(repo_root)
    train_wagon_edges = [
        e
        for e in graph.edges
        if e.edge_type == EdgeType.INCLUDES
        and e.source_urn.startswith("train:")
        and e.target_urn == "wagon:aggregate-bank-data"
    ]
    LOG.info("train→wagon edges built from participants: %d", len(train_wagon_edges))
    assert len(train_wagon_edges) >= 1, (
        "Expected ≥1 train→wagon INCLUDES edge from `participants`. "
        f"Got {len(train_wagon_edges)}. All edges: "
        f"{[(e.source_urn, e.target_urn, e.edge_type.value) for e in graph.edges]}"
    )


def test_legacy_wagons_field_still_produces_includes_edge(tmp_path):
    """
    GIVEN a pre-1.56 train YAML with only the legacy `wagons` field
    WHEN _build_train_edges runs
    THEN the `train → wagon INCLUDES` edge must still be built.

    Guarantees backward compatibility for plan/ trees that have not yet
    migrated to the `participants` field.
    """
    repo_root = tmp_path
    plan = repo_root / "plan"
    plan.mkdir()
    _write_minimal_wagon(plan, "aggregate-bank-data")
    _write_train(
        plan,
        "0002-legacy",
        "\n".join(
            [
                'train_id: "0002-legacy"',
                'title: "Legacy wagons field"',
                'description: "Legacy train using pre-participants field"',
                "themes: [commons]",
                'wagons: ["aggregate-bank-data"]',
                "",
            ]
        ),
    )

    graph = _build_graph(repo_root)
    assert _count_train_wagon_edges(graph) >= 1, (
        "Legacy `wagons` field must still produce train→wagon edges. "
        "Backward compatibility has regressed."
    )


def test_mixed_participants_and_wagons_do_not_duplicate_edges(tmp_path):
    """
    GIVEN a train YAML that declares BOTH `participants` and `wagons`
      pointing at the same wagon (the documented workaround for #285)
    WHEN _build_train_edges runs
    THEN exactly one `train → wagon INCLUDES` edge must be emitted,
      not two.
    """
    repo_root = tmp_path
    plan = repo_root / "plan"
    plan.mkdir()
    _write_minimal_wagon(plan, "aggregate-bank-data")
    _write_train(
        plan,
        "0003-mixed",
        "\n".join(
            [
                'train_id: "0003-mixed"',
                'title: "Mixed fields"',
                'description: "Both participants and wagons declared"',
                "themes: [commons]",
                'participants: ["wagon:aggregate-bank-data"]',
                'wagons: ["aggregate-bank-data"]',
                "",
            ]
        ),
    )

    graph = _build_graph(repo_root)
    train_wagon_edges = [
        e
        for e in graph.edges
        if e.edge_type == EdgeType.INCLUDES
        and e.source_urn == "train:0003-mixed"
        and e.target_urn == "wagon:aggregate-bank-data"
    ]
    assert len(train_wagon_edges) == 1, (
        f"Expected exactly 1 train→wagon edge when both fields are declared, "
        f"got {len(train_wagon_edges)}. Duplicate INCLUDES edges break visualizer styling."
    )


def test_non_wagon_participants_are_filtered_out(tmp_path):
    """
    GIVEN a train YAML whose `participants` list contains `user:*` and
      `system:*` URNs alongside a wagon URN
    WHEN _build_train_edges runs
    THEN only the `wagon:*` participants must become `train → wagon INCLUDES`
      edges — no phantom `wagon:user`, `wagon:customer`, or `wagon:system` edges.

    `INCLUDES` is strictly a train-contains-wagon relation. Typed edges for
    user/system actors are tracked as a separate follow-up.
    """
    repo_root = tmp_path
    plan = repo_root / "plan"
    plan.mkdir()
    _write_minimal_wagon(plan, "aggregate-bank-data")
    _write_train(
        plan,
        "0004-actors",
        "\n".join(
            [
                'train_id: "0004-actors"',
                'title: "Train with user and system actors"',
                'description: "Mixed-actor participants list"',
                "themes: [commons]",
                "participants:",
                '  - "wagon:aggregate-bank-data"',
                '  - "user:customer"',
                '  - "system:payment-gateway"',
                "",
            ]
        ),
    )

    graph = _build_graph(repo_root)

    train_source_edges = [
        e
        for e in graph.edges
        if e.edge_type == EdgeType.INCLUDES and e.source_urn == "train:0004-actors"
    ]
    targets = {e.target_urn for e in train_source_edges}
    LOG.info("train:0004-actors INCLUDES targets: %s", sorted(targets))

    assert "wagon:aggregate-bank-data" in targets, (
        "Wagon participant must produce an INCLUDES edge"
    )
    phantom_targets = {
        t
        for t in targets
        if t in {"wagon:customer", "wagon:payment-gateway", "wagon:user", "wagon:system"}
    }
    assert not phantom_targets, (
        f"user:*/system:* participants must not produce wagon edges. "
        f"Phantom targets: {sorted(phantom_targets)}"
    )
