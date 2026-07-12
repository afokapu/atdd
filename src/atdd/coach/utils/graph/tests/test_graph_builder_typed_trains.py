# URN: test:coach:graph-builder:typed-trains-and-registry-files
# Issue: #1440 (follows #1421)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1440 — the graph builder must find TYPED trains, and must never mistake a
registry/alias file for one.

``_build_train_edges`` globs ``plan/_trains/*.yaml`` — a FLAT scan. #1421 moved
every train to ``plan/_trains/<subject>/<slug>.yaml``, so that glob now matches
exactly one thing in the real repo: ``_aliases.yaml``, the migration alias map,
which is not a train at all. The consequences:

  * every typed train gets ZERO containment (INCLUDES) and ZERO TRAIN_STEP edges
    — the train half of the graph is silently empty, and
  * the only file the scan does see is a registry file it has no business
    reading as a train detail file.

It also derived a train's category from ``train_id[1]`` — the identity digit
#1421 retired. A typed identity has no digit there, so the category must come
from the train's ``category`` FIELD.
"""
from __future__ import annotations

from pathlib import Path

from atdd.coach.utils.graph.graph_builder import (
    EdgeType,
    GraphBuilder,
    TraceabilityGraph,
)

_ALIASES = """\
version: '1.0'
name: Train URN alias map
description: 'Migration alias map (#1421): legacy NNNN-slug -> typed train.'
aliases:
  0003-author-substrate: substrate/author-artifacts
"""


def _write_typed_train(plan: Path, subject: str, slug: str, category: str, body: str) -> None:
    d = plan / "_trains" / subject
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.yaml").write_text(
        "\n".join(
            [
                f"train_id: train:{subject}:{slug}",
                f'title: "{slug}"',
                f'description: "typed train for #1440"',
                f"category: {category}",
                "themes: [commons]",
                body,
            ]
        ),
        encoding="utf-8",
    )


def _write_aliases(plan: Path) -> None:
    d = plan / "_trains"
    d.mkdir(parents=True, exist_ok=True)
    (d / "_aliases.yaml").write_text(_ALIASES, encoding="utf-8")


def _build(repo_root: Path) -> TraceabilityGraph:
    builder = GraphBuilder(repo_root=repo_root, use_cache=False)
    graph = TraceabilityGraph()
    builder._build_train_edges(graph)
    return graph


def _steps(graph: TraceabilityGraph, train_urn: str | None = None):
    out = [e for e in graph.edges if e.edge_type == EdgeType.TRAIN_STEP]
    if train_urn is not None:
        out = [e for e in out if e.metadata.get("train") == train_urn]
    return out


# --------------------------------------------------------------------------- #
# a typed train must actually be found
# --------------------------------------------------------------------------- #
def test_typed_train_emits_containment_edges(tmp_path):
    """A train under plan/_trains/<subject>/<slug>.yaml contains its wagons.

    Today the flat glob never descends into the subject directory, so a typed
    train contributes nothing to the graph at all.
    """
    plan = tmp_path / "plan"
    _write_typed_train(
        plan, "substrate", "author-artifacts", "nominal",
        'participants: ["wagon:stage-request", "wagon:dispatch-call"]',
    )
    graph = _build(tmp_path)

    urn = "train:substrate:author-artifacts"
    includes = {
        e.target_urn for e in graph.edges
        if e.edge_type == EdgeType.INCLUDES and e.source_urn == urn
    }
    assert includes == {"wagon:stage-request", "wagon:dispatch-call"}


def test_typed_train_emits_train_step_edges(tmp_path):
    plan = tmp_path / "plan"
    _write_typed_train(
        plan, "substrate", "author-artifacts", "nominal",
        "\n".join([
            'participants: ["wagon:stage-request", "wagon:dispatch-call"]',
            "sequence:",
            "  - {step: 1, intent: prep, from: wagon:stage-request, to: wagon:stage-request, artifact: x}",
            "  - {step: 2, intent: handoff, from: wagon:stage-request, to: wagon:dispatch-call, artifact: x}",
        ]),
    )
    graph = _build(tmp_path)

    edges = _steps(graph, "train:substrate:author-artifacts")
    assert len(edges) == 1, "the one wagon->wagon handoff must emit one TRAIN_STEP edge"
    assert edges[0].source_urn == "wagon:stage-request"
    assert edges[0].target_urn == "wagon:dispatch-call"
    assert edges[0].metadata["step"] == 2


def test_train_step_category_comes_from_the_category_field(tmp_path):
    """Category is a FIELD (#1421). A typed identity has no digit to parse."""
    plan = tmp_path / "plan"
    _write_typed_train(
        plan, "match-resolution", "timeout", "alternate",
        "\n".join([
            'participants: ["wagon:a", "wagon:b"]',
            "sequence:",
            "  - {step: 1, intent: handoff, from: wagon:a, to: wagon:b, artifact: x}",
        ]),
    )
    graph = _build(tmp_path)

    edges = _steps(graph, "train:match-resolution:timeout")
    assert len(edges) == 1
    assert edges[0].metadata["category"] == "alternate", (
        "the category must be read from the train's `category` field, not derived "
        "by indexing the identity"
    )


# --------------------------------------------------------------------------- #
# a registry/alias file is NOT a train
# --------------------------------------------------------------------------- #
def test_alias_registry_file_never_yields_a_train(tmp_path):
    """``_aliases.yaml`` is the migration alias map, not a train detail file.

    It declares no train_id, so nothing may mint a ``train:_aliases`` URN from
    its stem or hang edges off it.
    """
    plan = tmp_path / "plan"
    _write_aliases(plan)
    _write_typed_train(
        plan, "substrate", "author-artifacts", "nominal",
        'participants: ["wagon:stage-request"]',
    )
    graph = _build(tmp_path)

    assert graph.get_node("train:_aliases") is None
    touched = {e.source_urn for e in graph.edges} | {e.target_urn for e in graph.edges}
    touched |= {e.metadata.get("train") for e in graph.edges}
    assert "train:_aliases" not in touched


def test_resolver_declarations_skip_registry_files(tmp_path):
    """``atdd repo broken`` resolves train URNs through ``TrainResolver``, so pin
    the registry-file skip there too — that is the path that would surface a
    bogus ``train:_aliases`` as a broken URN.
    """
    from atdd.coach.utils.graph.resolver import TrainResolver

    plan = tmp_path / "plan"
    _write_aliases(plan)
    (plan / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")
    _write_typed_train(
        plan, "substrate", "author-artifacts", "nominal",
        'participants: ["wagon:stage-request"]',
    )

    urns = {d.urn for d in TrainResolver(tmp_path).find_declarations()}

    assert urns == {"train:substrate:author-artifacts"}
    assert not any("_aliases" in u or "_trains" in u for u in urns)
