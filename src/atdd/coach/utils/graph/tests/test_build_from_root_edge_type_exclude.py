# URN: test:coach:graph_builder:build_from_root_edge_type_exclude
"""
Regression test for issue #287 PR 2: GraphBuilder.build_from_root must
pipe the `edge_type_exclude` parameter through to TraceabilityGraph
.get_subgraph, so the viz `Structural` mode can hide TRAIN_STEP edges
via the same filter contract that PR 1 added to get_subgraph.

This is a thin plumbing test — the underlying exclusion logic is already
pinned by test_get_subgraph_edge_type_exclude.py. What we check here is
that the builder-level entry point doesn't silently drop the parameter.
"""

from __future__ import annotations

from pathlib import Path

from atdd.coach.utils.graph.graph_builder import (
    EdgeType,
    GraphBuilder,
)


def _write_wagon(plan: Path, slug: str) -> None:
    d = plan / slug.replace("-", "_")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"_{slug.replace('-', '_')}.yaml").write_text(
        "\n".join(
            [
                f"wagon: {slug}",
                f"urn: wagon:{slug}",
                'description: "x"',
                "theme: commons",
                'subject: "s"',
                'context: "c"',
                'action: "a"',
                'goal: "g"',
                'outcome: "o"',
                "produce: []",
                "consume: []",
                "wmbt: {total: 0}",
                "",
            ]
        )
    )


def _write_train(plan: Path, train_id: str, body: str) -> None:
    trains = plan / "_trains"
    trains.mkdir(parents=True, exist_ok=True)
    (trains / f"{train_id}.yaml").write_text(body)


def test_build_from_root_pipes_edge_type_exclude_through(tmp_path):
    """
    Given a repo with one two-wagon train that would normally emit a
    TRAIN_STEP edge between its wagons, building a subgraph rooted at the
    upstream wagon with `edge_type_exclude={TRAIN_STEP}` must NOT pull in
    the downstream wagon (no leak via the handoff).
    """
    plan = tmp_path / "plan"
    plan.mkdir()
    _write_wagon(plan, "stage")
    _write_wagon(plan, "dispatch")
    _write_train(
        plan,
        "0205-alt",
        "\n".join(
            [
                'train_id: "0205-alt"',
                'title: "alt"',
                'description: "two-wagon handoff"',
                "themes: [commons]",
                'participants: ["wagon:stage", "wagon:dispatch"]',
                "sequence:",
                "  - {step: 1, intent: x, from: wagon:stage, to: wagon:dispatch, artifact: x}",
                "",
            ]
        ),
    )

    builder = GraphBuilder(repo_root=tmp_path, use_cache=False)
    sub = builder.build_from_root(
        "wagon:stage",
        max_depth=-1,
        edge_type_exclude={EdgeType.TRAIN_STEP},
    )
    assert "wagon:dispatch" not in sub.nodes, (
        "edge_type_exclude must prevent the wagon-rooted subgraph from "
        "leaking into the handoff target"
    )


def test_build_from_root_default_leaves_exclude_none(tmp_path):
    """
    Backward-compat guard: callers passing no exclude must see pre-PR-2
    behavior (TRAIN_STEP edges traversed normally).
    """
    plan = tmp_path / "plan"
    plan.mkdir()
    _write_wagon(plan, "stage")
    _write_wagon(plan, "dispatch")
    _write_train(
        plan,
        "0205-alt",
        "\n".join(
            [
                'train_id: "0205-alt"',
                'title: "alt"',
                'description: "two-wagon handoff"',
                "themes: [commons]",
                'participants: ["wagon:stage", "wagon:dispatch"]',
                "sequence:",
                "  - {step: 1, intent: x, from: wagon:stage, to: wagon:dispatch, artifact: x}",
                "",
            ]
        ),
    )

    builder = GraphBuilder(repo_root=tmp_path, use_cache=False)
    sub = builder.build_from_root("wagon:stage", max_depth=-1)
    assert "wagon:dispatch" in sub.nodes, (
        "Without exclude, TRAIN_STEP should be traversed as before"
    )
