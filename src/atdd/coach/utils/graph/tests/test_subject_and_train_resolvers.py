# URN: test:coach:graph:subject-and-train-resolvers
"""
Graph & resolver behavior for the typed URN grammar (issue #1421, worker C2).

Covers three things the engine refactor (C1) requires downstream:

- ``SubjectResolver`` — the new ``subject:<name>`` root family resolves against
  the subject registry (``plan/_subjects.yaml``) and tolerates its absence.
- ``TrainResolver`` — the typed ``train:<subject>:<slug>`` form resolves to the
  nested ``plan/_trains/<subject>/<slug>.yaml`` file (path reconstructs
  ``subject/slug``), and a legacy ``train:NNNN-slug`` URN STILL resolves via the
  migration alias map or a flat-path fallback (dual-resolution).
- Graph topology — ``subject`` is a root family (SEGMENT_COUNTS count == 1) and a
  typed 2-token ``train`` is NOT a false-positive orphan; it is parented via a
  ``subject -> train`` CONTAINS edge.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.coach.utils.graph.resolver import (
    ResolverRegistry,
    SubjectResolver,
    TrainResolver,
)
from atdd.coach.utils.graph.graph_builder import (
    EdgeType,
    GraphBuilder,
    TraceabilityGraph,
    URNEdge,
    URNNode,
)
from atdd.coach.utils.graph.edge_validator import EdgeValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_subjects(plan: Path, entries: list) -> Path:
    plan.mkdir(parents=True, exist_ok=True)
    path = plan / "_subjects.yaml"
    path.write_text(yaml.safe_dump({"subjects": entries}, sort_keys=False))
    return path


def _write_typed_train(plan: Path, subject: str, slug: str, body: str = "") -> Path:
    d = plan / "_trains" / subject
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{slug}.yaml"
    f.write_text(body or f"id: train:{subject}:{slug}\ndescription: typed train\n")
    return f


def _write_flat_train(plan: Path, train_id: str, body: str = "") -> Path:
    d = plan / "_trains"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{train_id}.yaml"
    f.write_text(body or f"train_id: {train_id}\ndescription: legacy train\n")
    return f


def _write_alias_map(plan: Path, mapping: dict) -> Path:
    d = plan / "_trains"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "_aliases.yaml"
    path.write_text(yaml.safe_dump({"aliases": mapping}, sort_keys=False))
    return path


# ---------------------------------------------------------------------------
# SubjectResolver
# ---------------------------------------------------------------------------


def test_subject_resolver_family_and_can_resolve(tmp_path):
    r = SubjectResolver(repo_root=tmp_path)
    assert r.family == "subject"
    assert r.can_resolve("subject:artifact-identity")
    assert not r.can_resolve("train:artifact-identity:migrate")


def test_subject_resolver_resolves_registered_subject(tmp_path):
    plan = tmp_path / "plan"
    registry = _write_subjects(
        plan,
        [
            {
                "subject": "artifact-identity",
                "title": "Artifact identity",
                "description": "Durable noun object of the migration.",
                "status": "active",
            }
        ],
    )
    r = SubjectResolver(repo_root=tmp_path)
    res = r.resolve("subject:artifact-identity")
    assert res.is_resolved, res.error
    assert res.resolved_paths == [registry]
    assert res.is_deterministic


def test_subject_resolver_unknown_subject_is_unresolved_not_crash(tmp_path):
    plan = tmp_path / "plan"
    _write_subjects(plan, [{"subject": "artifact-identity"}])
    r = SubjectResolver(repo_root=tmp_path)
    res = r.resolve("subject:not-registered")
    assert res.is_broken
    assert not res.resolved_paths


def test_subject_resolver_missing_registry_is_graceful(tmp_path):
    # No plan/_subjects.yaml at all — the family exists before the registry is
    # authored during migration. Must not raise.
    r = SubjectResolver(repo_root=tmp_path)
    res = r.resolve("subject:artifact-identity")
    assert res.is_broken
    assert not res.resolved_paths


def test_subject_resolver_find_declarations(tmp_path):
    plan = tmp_path / "plan"
    _write_subjects(
        plan,
        [
            {"subject": "artifact-identity", "title": "A"},
            {"subject": "issue-lifecycle", "title": "B"},
        ],
    )
    r = SubjectResolver(repo_root=tmp_path)
    urns = {d.urn for d in r.find_declarations()}
    assert urns == {"subject:artifact-identity", "subject:issue-lifecycle"}


def test_registry_routes_subject_to_subject_resolver(tmp_path):
    plan = tmp_path / "plan"
    _write_subjects(plan, [{"subject": "artifact-identity"}])
    reg = ResolverRegistry(repo_root=tmp_path)
    assert isinstance(reg.get_resolver("subject"), SubjectResolver)
    res = reg.resolve("subject:artifact-identity")
    assert res.is_resolved, res.error


# ---------------------------------------------------------------------------
# TrainResolver — typed grammar
# ---------------------------------------------------------------------------


def test_train_resolver_typed_resolves_nested_path(tmp_path):
    plan = tmp_path / "plan"
    train_file = _write_typed_train(plan, "artifact-identity", "migrate-with-alias")
    r = TrainResolver(repo_root=tmp_path)
    res = r.resolve("train:artifact-identity:migrate-with-alias")
    assert res.is_resolved, res.error
    assert res.resolved_paths == [train_file]
    assert res.is_deterministic


def test_train_resolver_typed_missing_file_is_unresolved(tmp_path):
    (tmp_path / "plan" / "_trains").mkdir(parents=True)
    r = TrainResolver(repo_root=tmp_path)
    res = r.resolve("train:artifact-identity:nope")
    assert res.is_broken
    assert not res.resolved_paths


def test_train_resolver_typed_find_declarations_reconstructs_subject_slug(tmp_path):
    plan = tmp_path / "plan"
    _write_typed_train(plan, "artifact-identity", "migrate-with-alias")
    _write_typed_train(plan, "substrate", "author-artifacts")
    r = TrainResolver(repo_root=tmp_path)
    urns = {d.urn for d in r.find_declarations()}
    assert "train:artifact-identity:migrate-with-alias" in urns
    assert "train:substrate:author-artifacts" in urns


# ---------------------------------------------------------------------------
# TrainResolver — legacy dual-resolution
# ---------------------------------------------------------------------------


def test_train_resolver_legacy_resolves_via_alias_map(tmp_path):
    plan = tmp_path / "plan"
    # Migrated file lives at the typed nested path...
    typed_file = _write_typed_train(plan, "self-compliance", "validate-lifecycle")
    # ...and the alias map maps the legacy id to it (subject/slug notation).
    _write_alias_map(
        plan,
        {"0001-self-compliance-validate": "self-compliance/validate-lifecycle"},
    )
    r = TrainResolver(repo_root=tmp_path)
    res = r.resolve("train:0001-self-compliance-validate")
    assert res.is_resolved, res.error
    assert res.resolved_paths == [typed_file]
    assert res.metadata.get("alias_of") == "train:self-compliance:validate-lifecycle"


def test_train_resolver_legacy_falls_back_to_flat_path(tmp_path):
    plan = tmp_path / "plan"
    flat = _write_flat_train(plan, "0002-coach-drives-lifecycle")
    r = TrainResolver(repo_root=tmp_path)
    # No alias map present — must still resolve via the flat legacy file.
    res = r.resolve("train:0002-coach-drives-lifecycle")
    assert res.is_resolved, res.error
    assert res.resolved_paths == [flat]


def test_train_resolver_legacy_unresolved_is_graceful(tmp_path):
    (tmp_path / "plan" / "_trains").mkdir(parents=True)
    r = TrainResolver(repo_root=tmp_path)
    res = r.resolve("train:0009-does-not-exist")
    assert res.is_broken
    assert not res.resolved_paths


# ---------------------------------------------------------------------------
# Graph topology — subject root + typed train parented (not orphan)
# ---------------------------------------------------------------------------


def test_subject_is_a_root_family_in_edge_validator(tmp_path):
    graph = TraceabilityGraph()
    validator = EdgeValidator(graph)
    # Derived from URNGrammar.SEGMENT_COUNTS (count == 1 => root).
    assert "subject" in validator._root_families


def test_build_subject_edges_parents_typed_train_on_subject(tmp_path):
    graph = TraceabilityGraph()
    graph.add_node(URNNode(urn="subject:artifact-identity", family="subject"))
    graph.add_node(
        URNNode(urn="train:artifact-identity:migrate-with-alias", family="train")
    )
    # A legacy 1-token train must NOT get a subject edge.
    graph.add_node(URNNode(urn="train:0001-self-compliance-validate", family="train"))

    builder = GraphBuilder(repo_root=tmp_path, use_cache=False)
    builder._build_subject_edges(graph)

    contains = [
        (e.source_urn, e.target_urn)
        for e in graph.edges
        if e.edge_type == EdgeType.CONTAINS
    ]
    assert (
        "subject:artifact-identity",
        "train:artifact-identity:migrate-with-alias",
    ) in contains
    # No subject parent synthesized for the legacy train.
    assert not any(
        t == "train:0001-self-compliance-validate" for _, t in contains
    )


def test_typed_train_is_not_flagged_orphan(tmp_path):
    graph = TraceabilityGraph()
    graph.add_node(URNNode(urn="subject:artifact-identity", family="subject"))
    graph.add_node(
        URNNode(urn="train:artifact-identity:migrate-with-alias", family="train")
    )
    graph.add_edge(
        URNEdge(
            source_urn="subject:artifact-identity",
            target_urn="train:artifact-identity:migrate-with-alias",
            edge_type=EdgeType.CONTAINS,
        )
    )
    validator = EdgeValidator(graph)
    orphan_urns = {i.urn for i in validator.find_orphans()}
    assert "subject:artifact-identity" not in orphan_urns
    assert "train:artifact-identity:migrate-with-alias" not in orphan_urns
