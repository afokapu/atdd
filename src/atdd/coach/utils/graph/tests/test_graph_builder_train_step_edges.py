# URN: test:coach:graph_builder:train_step_edges
"""
Regression test for issue #287: TRAIN_STEP edges from train sequence[] handoffs.

The URN graph must encode the ordered wagon-to-wagon handoffs inside each
train's sequence[] as first-class edges, so per-train subgraph consumers
(notably the new viz journey mode) can render pipelines linearly without
re-parsing YAML.

Rules pinned here:
  - One TRAIN_STEP edge per sequence[] entry where
    `from != to` and both are wagon:* URNs ("handoff").
  - Internal-phase steps (`from == to`) are skipped — they don't advance
    the pipeline and would clutter the journey-mode render.
  - Non-wagon participants on from/to (user:*, system:*) are ignored.
  - Each emitted edge carries metadata {train, step, intent, category, source},
    where `category` is read from the train's `category` FIELD (#1421/#1440),
    never derived by indexing the identity.
  - Multiple trains traversing the same handoff each emit their own edge
    (parallel edges, filterable by metadata.train).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from atdd.coach.utils.graph.graph_builder import (
    EdgeType,
    GraphBuilder,
    TraceabilityGraph,
)

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_wagon(plan_dir: Path, slug: str) -> None:
    wagon_dir = plan_dir / slug.replace("-", "_")
    wagon_dir.mkdir(parents=True, exist_ok=True)
    wagon_file = wagon_dir / f"_{slug.replace('-', '_')}.yaml"
    wagon_file.write_text(
        "\n".join(
            [
                f"wagon: {slug}",
                f"urn: wagon:{slug}",
                'description: "wagon for TRAIN_STEP regression test"',
                "theme: commons",
                'subject: "test:worker"',
                'context: "test"',
                'action: "x"',
                'goal: "y"',
                'outcome: "z"',
                "produce: []",
                "consume: []",
                "wmbt:",
                "  total: 0",
                "",
            ]
        )
    )


def _write_train(plan_dir: Path, train_id: str, body: str) -> None:
    trains_dir = plan_dir / "_trains"
    trains_dir.mkdir(parents=True, exist_ok=True)
    (trains_dir / f"{train_id}.yaml").write_text(body)


def _build(repo_root: Path) -> TraceabilityGraph:
    builder = GraphBuilder(repo_root=repo_root, use_cache=False)
    graph = TraceabilityGraph()
    builder._build_train_edges(graph)
    return graph


def _train_step_edges(graph: TraceabilityGraph, train_urn: str | None = None):
    out = [e for e in graph.edges if e.edge_type == EdgeType.TRAIN_STEP]
    if train_urn is not None:
        out = [e for e in out if e.metadata.get("train") == train_urn]
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_single_wagon_train_emits_no_train_step_edges(tmp_path):
    """
    A train whose only sequence entry is an internal-phase step (from==to)
    must not produce any TRAIN_STEP edges. There are no handoffs.
    """
    plan = tmp_path / "plan"
    plan.mkdir()
    _write_wagon(plan, "dispatch-call")
    _write_train(
        plan,
        "0001-first-run-nominal",
        "\n".join(
            [
                'train_id: "0001-first-run-nominal"',
                'title: "First run nominal"',
                'description: "Single-wagon internal-phase only"',
                "themes: [commons]",
                'participants: ["wagon:dispatch-call"]',
                "sequence:",
                "  - step: 1",
                '    intent: "internal prep"',
                "    from: wagon:dispatch-call",
                "    to:   wagon:dispatch-call",
                '    artifact: "dispatch:scenario-step"',
                "",
            ]
        ),
    )
    graph = _build(plan.parent)
    assert _train_step_edges(graph) == [], (
        "Single-wagon train (internal-phase only) must emit zero TRAIN_STEP edges"
    )


def test_two_wagon_handoff_emits_one_train_step_edge_with_metadata(tmp_path):
    """
    A two-wagon train with one handoff must produce exactly one TRAIN_STEP
    edge whose metadata captures train/step/intent/category/source.
    """
    plan = tmp_path / "plan"
    plan.mkdir()
    _write_wagon(plan, "stage-request")
    _write_wagon(plan, "dispatch-call")
    _write_train(
        plan,
        "0205-renewal-before-deadline",
        "\n".join(
            [
                'train_id: "0205-renewal-before-deadline"',
                'title: "Renewal before deadline"',
                'description: "Alternate scenario: stage -> dispatch handoff"',
                "category: alternate",
                "themes: [commons]",
                "participants:",
                "  - wagon:stage-request",
                "  - wagon:dispatch-call",
                "sequence:",
                "  - step: 1",
                '    intent: "Prepare inputs"',
                "    from: wagon:stage-request",
                "    to:   wagon:stage-request",
                '    artifact: "stage:scenario-step"',
                "  - step: 2",
                '    intent: "Hand off to dispatch and issue request"',
                "    from: wagon:stage-request",
                "    to:   wagon:dispatch-call",
                '    artifact: "dispatch:scenario-step"',
                "",
            ]
        ),
    )
    graph = _build(plan.parent)
    edges = _train_step_edges(graph, "train:0205-renewal-before-deadline")
    assert len(edges) == 1, (
        f"Expected exactly 1 TRAIN_STEP edge for the single handoff; got {len(edges)}"
    )
    e = edges[0]
    assert e.source_urn == "wagon:stage-request"
    assert e.target_urn == "wagon:dispatch-call"
    assert e.metadata["train"] == "train:0205-renewal-before-deadline"
    assert e.metadata["step"] == 2
    assert "Hand off" in e.metadata["intent"]
    assert e.metadata["category"] == "alternate", (
        "category is read from the train's `category` field; got "
        f"{e.metadata.get('category')!r}"
    )
    assert e.metadata["source"] == "train-sequence"


def test_internal_phase_steps_are_skipped(tmp_path):
    """
    A train with multiple internal-phase steps and one real handoff must
    emit exactly one TRAIN_STEP edge — the handoff. Self-loops never materialize.
    """
    plan = tmp_path / "plan"
    plan.mkdir()
    _write_wagon(plan, "a")
    _write_wagon(plan, "b")
    _write_train(
        plan,
        "0102-redirect-timeout",
        "\n".join(
            [
                'train_id: "0102-redirect-timeout"',
                'title: "Error scenario"',
                'description: "Error scenario; two internal steps, one handoff"',
                "category: error",
                "themes: [commons]",
                'participants: ["wagon:a", "wagon:b"]',
                "sequence:",
                "  - {step: 1, intent: internal, from: wagon:a, to: wagon:a, artifact: x}",
                "  - {step: 2, intent: handoff, from: wagon:a, to: wagon:b, artifact: x}",
                "  - {step: 3, intent: internal, from: wagon:b, to: wagon:b, artifact: x}",
                "",
            ]
        ),
    )
    graph = _build(plan.parent)
    edges = _train_step_edges(graph, "train:0102-redirect-timeout")
    assert len(edges) == 1
    assert edges[0].source_urn == "wagon:a"
    assert edges[0].target_urn == "wagon:b"
    assert edges[0].metadata["category"] == "error"


def test_non_wagon_participants_in_sequence_are_ignored(tmp_path):
    """
    sequence[] entries whose from/to are user:*/system:* (not wagon:*) must
    not produce TRAIN_STEP edges. TRAIN_STEP is strictly wagon-to-wagon.
    """
    plan = tmp_path / "plan"
    plan.mkdir()
    _write_wagon(plan, "a")
    _write_train(
        plan,
        "0001-actor-edges",
        "\n".join(
            [
                'train_id: "0001-actor-edges"',
                'title: "User/system actors"',
                'description: "Ensure non-wagon sides are ignored"',
                "themes: [commons]",
                'participants: ["wagon:a", "user:customer"]',
                "sequence:",
                "  - {step: 1, intent: x, from: user:customer, to: wagon:a, artifact: x}",
                "  - {step: 2, intent: x, from: wagon:a, to: system:payment, artifact: x}",
                "",
            ]
        ),
    )
    graph = _build(plan.parent)
    edges = _train_step_edges(graph, "train:0001-actor-edges")
    assert edges == [], (
        f"Non-wagon sides must not produce TRAIN_STEP edges; got {edges}"
    )


def test_multiple_trains_overlapping_handoff_emit_parallel_edges(tmp_path):
    """
    Three trains traversing the same wagon→wagon handoff must each produce
    their own TRAIN_STEP edge. The underlying graph holds three parallel
    edges, distinguishable by metadata.train — journey mode always filters
    to one train at render time so this is not a visual problem.
    """
    plan = tmp_path / "plan"
    plan.mkdir()
    _write_wagon(plan, "stage-request")
    _write_wagon(plan, "dispatch-call")
    for tid, cat in [
        ("0205-renewal-before-deadline", "alternate"),
        ("0105-deadline-expired-silently", "error"),
        ("0201-first-flow-via-stage", "alternate"),
    ]:
        _write_train(
            plan,
            tid,
            "\n".join(
                [
                    f'train_id: "{tid}"',
                    f'title: "{tid}"',
                    f'description: "Shares stage->dispatch handoff ({cat})"',
                    f"category: {cat}",
                    "themes: [commons]",
                    'participants: ["wagon:stage-request", "wagon:dispatch-call"]',
                    "sequence:",
                    "  - {step: 1, intent: handoff, from: wagon:stage-request, to: wagon:dispatch-call, artifact: x}",
                    "",
                ]
            ),
        )
    graph = _build(plan.parent)
    edges = [
        e
        for e in graph.edges
        if e.edge_type == EdgeType.TRAIN_STEP
        and e.source_urn == "wagon:stage-request"
        and e.target_urn == "wagon:dispatch-call"
    ]
    LOG.info("parallel TRAIN_STEP edges on shared handoff: %d", len(edges))
    assert len(edges) == 3, (
        f"Each overlapping train must emit its own TRAIN_STEP edge; got {len(edges)}"
    )
    train_urns = {e.metadata["train"] for e in edges}
    assert train_urns == {
        "train:0205-renewal-before-deadline",
        "train:0105-deadline-expired-silently",
        "train:0201-first-flow-via-stage",
    }
    categories = {e.metadata["category"] for e in edges}
    assert categories == {"alternate", "error"}, (
        f"Categories must come from each train's `category` field; got {categories}"
    )
