# URN: test:coach:graph_builder:security_edges
"""
Acceptance tests for SecurityResolver integration into GraphBuilder (#419).

Covers:
  - feature -> security CONTAINS edge per resolved abuse_case.
  - security -> acceptance_ref REFERENCES edge per declared abuse_case.
  - REFERENCES edge is emitted regardless of whether the target acc URN
    resolves; broken targets are surfaced via EdgeValidator.find_broken.
  - URNNode.metadata exposes abuse_case fields verbatim.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.graph.graph_builder import (
    EdgeType,
    GraphBuilder,
)
from atdd.coach.utils.graph.edge_validator import EdgeValidator, IssueType


_ABUSE_TWO = (
    '- id: "THREAT-001"\n'
    '  name: "Session token leak"\n'
    '  threat: "Attacker exfiltrates session token"\n'
    '  mitigation: "Bind tokens to IP and rotate"\n'
    '  severity: "high"\n'
    '  acceptance_ref: "acc:auth:E001-HTTP-001"\n'
    '- id: "THREAT-002"\n'
    '  name: "Replay attack"\n'
    '  threat: "Attacker replays captured session"\n'
    '  mitigation: "Nonce + timestamp validation"\n'
    '  severity: "medium"\n'
    '  acceptance_ref: "acc:auth:E001-HTTP-002"\n'
)


def _write_feature(plan_dir: Path, wagon_slug: str, feature_slug: str, abuse_yaml: str) -> Path:
    wagon_dir = plan_dir / wagon_slug.replace("-", "_")
    features_dir = wagon_dir / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    feature_file = features_dir / f"{feature_slug.replace('-', '_')}.yaml"
    indented = "\n".join(("    " + ln) if ln.strip() else ln for ln in abuse_yaml.splitlines())
    body = (
        f'urn: "feature:{wagon_slug}:{feature_slug}"\n'
        f'wagon: "wagon:{wagon_slug}"\n'
        'description: "Fixture feature for security edge tests"\n'
        "sizing:\n"
        "  wmbts: 0\n"
        "  footprint_score: 1\n"
        '  footprint_size: "S"\n'
        "wmbts: []\n"
        "components:\n"
        "  backend:\n"
        "    presentation: []\n"
        "    application: []\n"
        "    domain: []\n"
        "    integration: []\n"
        "security:\n"
        "  abuse_cases:\n"
    )
    body += indented + "\n"
    feature_file.write_text(body)
    return feature_file


def _write_minimal_wagon(plan_dir: Path, slug: str) -> Path:
    """Write a minimal wagon manifest so wagon URNs resolve."""
    wagon_dir = plan_dir / slug.replace("-", "_")
    wagon_dir.mkdir(parents=True, exist_ok=True)
    wagon_file = wagon_dir / f"_{slug.replace('-', '_')}.yaml"
    wagon_file.write_text(
        f'wagon: {slug}\n'
        f'urn: wagon:{slug}\n'
        'description: "Minimal wagon for security edge regression test"\n'
        "produce: []\n"
        "consume: []\n"
        "wmbt:\n"
        "  total: 0\n"
    )
    return wagon_file


def _build_graph(repo_root: Path):
    return GraphBuilder(repo_root=repo_root, use_cache=False).build()


def test_feature_to_security_contains_edge_emitted(tmp_path):
    """feature → security CONTAINS edge per abuse_case."""
    plan = tmp_path / "plan"
    _write_minimal_wagon(plan, "auth")
    _write_feature(plan, "auth", "session-management", _ABUSE_TWO)

    graph = _build_graph(tmp_path)

    contains_edges = [
        e
        for e in graph.edges
        if e.edge_type == EdgeType.CONTAINS
        and e.source_urn == "feature:auth:session-management"
        and e.target_urn.startswith("security:auth:session-management:")
    ]
    targets = sorted(e.target_urn for e in contains_edges)
    assert targets == [
        "security:auth:session-management:001",
        "security:auth:session-management:002",
    ]


def test_security_to_acceptance_references_edge_emitted(tmp_path):
    """security → acceptance_ref REFERENCES edge per declared abuse_case."""
    plan = tmp_path / "plan"
    _write_minimal_wagon(plan, "auth")
    _write_feature(plan, "auth", "session-management", _ABUSE_TWO)

    graph = _build_graph(tmp_path)

    references = [
        e
        for e in graph.edges
        if e.edge_type == EdgeType.REFERENCES
        and e.source_urn.startswith("security:auth:session-management:")
    ]
    pairs = {(e.source_urn, e.target_urn) for e in references}
    assert pairs == {
        ("security:auth:session-management:001", "acc:auth:E001-HTTP-001"),
        ("security:auth:session-management:002", "acc:auth:E001-HTTP-002"),
    }


def test_security_node_carries_abuse_case_metadata(tmp_path):
    """URNNode.metadata['declaration'] mirrors the abuse_case fields verbatim."""
    plan = tmp_path / "plan"
    _write_minimal_wagon(plan, "auth")
    _write_feature(plan, "auth", "session-management", _ABUSE_TWO)

    graph = _build_graph(tmp_path)
    node = graph.nodes["security:auth:session-management:001"]
    decl_meta = node.metadata.get("declaration") or {}
    assert decl_meta["id"] == "THREAT-001"
    assert decl_meta["name"] == "Session token leak"
    assert decl_meta["threat"] == "Attacker exfiltrates session token"
    assert decl_meta["mitigation"] == "Bind tokens to IP and rotate"
    assert decl_meta["severity"] == "high"
    assert decl_meta["acceptance_ref"] == "acc:auth:E001-HTTP-001"


def test_broken_acceptance_ref_is_flagged_by_validator(tmp_path):
    """
    An abuse_case whose acceptance_ref points at a non-existent acc URN
    must produce a broken-reference issue surfaced by EdgeValidator.
    """
    plan = tmp_path / "plan"
    _write_minimal_wagon(plan, "auth")
    _write_feature(plan, "auth", "session-management", _ABUSE_TWO)

    graph = _build_graph(tmp_path)
    issues = EdgeValidator(graph).find_broken()
    broken_acc_urns = {
        i.urn for i in issues if i.issue_type == IssueType.BROKEN and i.urn.startswith("acc:")
    }
    # The acc URNs referenced in _ABUSE_TWO have no backing WMBT/feature
    # YAML, so both should be flagged broken.
    assert "acc:auth:E001-HTTP-001" in broken_acc_urns
    assert "acc:auth:E001-HTTP-002" in broken_acc_urns


def test_abuse_case_without_acceptance_ref_emits_no_references_edge(tmp_path):
    """An abuse_case with no acceptance_ref produces only the CONTAINS edge."""
    plan = tmp_path / "plan"
    _write_minimal_wagon(plan, "auth")
    _write_feature(
        plan,
        "auth",
        "no-ref",
        (
            '- id: "THREAT-001"\n'
            '  name: "Token leak"\n'
            '  threat: "x"\n'
            '  mitigation: "y"\n'
            '  severity: "low"\n'
        ),
    )
    graph = _build_graph(tmp_path)

    refs = [
        e
        for e in graph.edges
        if e.edge_type == EdgeType.REFERENCES and e.source_urn.startswith("security:auth:no-ref:")
    ]
    contains = [
        e
        for e in graph.edges
        if e.edge_type == EdgeType.CONTAINS
        and e.source_urn == "feature:auth:no-ref"
        and e.target_urn.startswith("security:auth:no-ref:")
    ]
    assert refs == []
    assert len(contains) == 1
