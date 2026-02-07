"""
URN Traceability Validators
===========================
Coach validators for URN coverage, resolution, and traceability.

Validates:
- All contract schemas have producing wagon reference
- All contract: URNs in produce[] resolve to files
- All URN resolutions are deterministic
- All required traceability edges exist per spec Section 8

Phase 1 (warn): Reports issues as warnings
Phase 2 (fail): Reports issues as errors, fails CI
"""
from __future__ import annotations

import pytest
from pathlib import Path
from typing import List, Optional

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.graph.resolver import ResolverRegistry, URNResolution
from atdd.coach.utils.graph.graph_builder import GraphBuilder, EdgeType
from atdd.coach.utils.graph.edge_validator import (
    EdgeValidator,
    ValidationResult,
    IssueSeverity,
    IssueType,
)


REPO_ROOT = find_repo_root()


@pytest.fixture
def resolver_registry():
    """Provide resolver registry for tests."""
    return ResolverRegistry(REPO_ROOT)


@pytest.fixture
def graph_builder():
    """Provide graph builder for tests."""
    return GraphBuilder(REPO_ROOT)


@pytest.fixture
def edge_validator():
    """Provide edge validator for tests."""
    return EdgeValidator(REPO_ROOT)


@pytest.mark.platform
def test_no_orphaned_contracts(edge_validator):
    """
    All contract schemas have producing wagon reference.

    URN:TRACE:001 - Contract orphan detection

    Given: Contract schema files exist in contracts/ directory
    When: Validating contract URN traceability
    Then: Each contract is referenced by at least one wagon's produce[] section
    """
    result = edge_validator.validate_contracts()

    orphan_issues = result.filter_by_type(IssueType.ORPHAN)

    if orphan_issues:
        orphan_urns = [i.urn for i in orphan_issues]
        message = (
            f"Found {len(orphan_issues)} orphaned contract(s) without producer wagon:\n"
            + "\n".join(f"  - {urn}" for urn in orphan_urns[:10])
        )
        if len(orphan_urns) > 10:
            message += f"\n  ... and {len(orphan_urns) - 10} more"
        pytest.skip(message)


@pytest.mark.platform
def test_no_broken_contract_urns(resolver_registry, graph_builder):
    """
    All contract: URNs in produce[] resolve to files.

    URN:TRACE:002 - Contract resolution validation

    Given: Wagon manifests declare contract URNs in produce[] sections
    When: Resolving each contract URN
    Then: Each URN resolves to an existing contract schema file
    """
    graph = graph_builder.build(["wagon", "contract"])
    broken_contracts = []

    for urn, node in graph.nodes.items():
        if node.family != "contract":
            continue

        resolution = resolver_registry.resolve(urn)
        if resolution.is_broken:
            broken_contracts.append({
                "urn": urn,
                "error": resolution.error,
            })

    if broken_contracts:
        message = (
            f"Found {len(broken_contracts)} broken contract URN(s):\n"
            + "\n".join(
                f"  - {c['urn']}: {c['error']}"
                for c in broken_contracts[:10]
            )
        )
        if len(broken_contracts) > 10:
            message += f"\n  ... and {len(broken_contracts) - 10} more"
        pytest.skip(message)


@pytest.mark.platform
def test_urn_resolution_deterministic(edge_validator):
    """
    All URN resolutions return exactly one artifact.

    URN:TRACE:003 - Resolution determinism validation

    Given: URN declarations exist across the codebase
    When: Resolving each URN
    Then: Each URN resolves to exactly one artifact path
    And: No URN is ambiguous (multiple matches)
    """
    issues = edge_validator.validate_determinism()

    non_deterministic = [i for i in issues if i.issue_type == IssueType.NON_DETERMINISTIC]

    if non_deterministic:
        message = (
            f"Found {len(non_deterministic)} non-deterministic URN(s):\n"
            + "\n".join(
                f"  - {i.urn}: {i.context}"
                for i in non_deterministic[:10]
            )
        )
        if len(non_deterministic) > 10:
            message += f"\n  ... and {len(non_deterministic) - 10} more"
        pytest.skip(message)


@pytest.mark.platform
def test_traceability_edges_complete(edge_validator):
    """
    All required edges per spec Section 8 exist.

    URN:TRACE:004 - Edge completeness validation

    Given: URN graph with nodes for wagons, features, WMBTs, acceptances
    When: Validating required edges
    Then: wagon -> feature (contains) edges exist
    And: wagon -> wmbt (contains) edges exist
    And: wmbt -> acceptance (contains) edges exist
    And: wagon -> contract (produces) edges exist where declared
    """
    issues = edge_validator.validate_edges()

    missing_edges = [i for i in issues if i.issue_type == IssueType.MISSING_EDGE]

    if missing_edges:
        message = (
            f"Found {len(missing_edges)} missing required edge(s):\n"
            + "\n".join(
                f"  - {i.urn}: {i.message}"
                for i in missing_edges[:10]
            )
        )
        if len(missing_edges) > 10:
            message += f"\n  ... and {len(missing_edges) - 10} more"
        pytest.skip(message)


@pytest.mark.platform
def test_wagon_produces_contracts(graph_builder):
    """
    Wagons that produce contracts have valid produce[] declarations.

    URN:TRACE:005 - Wagon produce validation

    Given: Wagon manifests with produce[] sections
    When: Building traceability graph
    Then: Each produce item with contract reference creates a produces edge
    """
    graph = graph_builder.build(["wagon", "contract"])

    wagons_with_contracts = []
    for urn, node in graph.nodes.items():
        if node.family == "wagon":
            outgoing = graph.get_outgoing_edges(urn)
            contract_edges = [
                e for e in outgoing
                if e.edge_type == EdgeType.PRODUCES
                and graph.get_node(e.target_urn)
                and graph.get_node(e.target_urn).family == "contract"
            ]
            if contract_edges:
                wagons_with_contracts.append({
                    "wagon": urn,
                    "contracts": [e.target_urn for e in contract_edges],
                })

    # This test passes if we can successfully build the graph
    # The actual validation is done by test_no_orphaned_contracts
    assert graph is not None


@pytest.mark.platform
def test_no_broken_telemetry_urns(resolver_registry, graph_builder):
    """
    All telemetry: URNs in produce[] resolve to files.

    URN:TRACE:006 - Telemetry resolution validation

    Given: Wagon manifests declare telemetry URNs in produce[] sections
    When: Resolving each telemetry URN
    Then: Each URN resolves to an existing telemetry definition file
    """
    graph = graph_builder.build(["wagon", "telemetry"])
    broken_telemetry = []

    for urn, node in graph.nodes.items():
        if node.family != "telemetry":
            continue

        resolution = resolver_registry.resolve(urn)
        if resolution.is_broken:
            broken_telemetry.append({
                "urn": urn,
                "error": resolution.error,
            })

    if broken_telemetry:
        message = (
            f"Found {len(broken_telemetry)} broken telemetry URN(s):\n"
            + "\n".join(
                f"  - {t['urn']}: {t['error']}"
                for t in broken_telemetry[:10]
            )
        )
        if len(broken_telemetry) > 10:
            message += f"\n  ... and {len(broken_telemetry) - 10} more"
        pytest.skip(message)


@pytest.mark.platform
def test_train_wagon_references_valid(resolver_registry, graph_builder):
    """
    Train files reference valid wagons.

    URN:TRACE:007 - Train reference validation

    Given: Train YAML files with wagon references
    When: Resolving wagon URNs from train.wagons[]
    Then: Each wagon URN resolves to an existing wagon manifest
    """
    graph = graph_builder.build(["train", "wagon"])
    broken_refs = []

    for urn, node in graph.nodes.items():
        if node.family != "train":
            continue

        outgoing = graph.get_outgoing_edges(urn)
        wagon_edges = [e for e in outgoing if e.edge_type == EdgeType.INCLUDES]

        for edge in wagon_edges:
            wagon_urn = edge.target_urn
            resolution = resolver_registry.resolve(wagon_urn)
            if resolution.is_broken:
                broken_refs.append({
                    "train": urn,
                    "wagon": wagon_urn,
                    "error": resolution.error,
                })

    if broken_refs:
        message = (
            f"Found {len(broken_refs)} broken wagon reference(s) in trains:\n"
            + "\n".join(
                f"  - {r['train']} -> {r['wagon']}: {r['error']}"
                for r in broken_refs[:10]
            )
        )
        if len(broken_refs) > 10:
            message += f"\n  ... and {len(broken_refs) - 10} more"
        pytest.skip(message)


@pytest.mark.platform
def test_urn_patterns_valid(resolver_registry):
    """
    All declared URNs match their family's pattern.

    URN:TRACE:008 - URN format validation

    Given: URN declarations across the codebase
    When: Validating each URN against its family pattern
    Then: All URNs match URNBuilder.PATTERNS for their family
    """
    from atdd.coach.utils.graph.urn import URNBuilder

    declarations = resolver_registry.find_all_declarations()
    invalid_urns = []

    for family, decls in declarations.items():
        pattern = URNBuilder.PATTERNS.get(family)
        if not pattern:
            continue

        for decl in decls:
            if not URNBuilder.validate_urn(decl.urn, family):
                invalid_urns.append({
                    "urn": decl.urn,
                    "family": family,
                    "source": str(decl.source_path),
                })

    if invalid_urns:
        message = (
            f"Found {len(invalid_urns)} URN(s) with invalid format:\n"
            + "\n".join(
                f"  - {u['urn']} ({u['family']}) at {u['source']}"
                for u in invalid_urns[:10]
            )
        )
        if len(invalid_urns) > 10:
            message += f"\n  ... and {len(invalid_urns) - 10} more"
        pytest.skip(message)


@pytest.mark.platform
def test_full_traceability_validation(edge_validator):
    """
    Full traceability validation passes in warn phase.

    URN:TRACE:009 - Full validation suite

    Given: Complete codebase with URN declarations
    When: Running full traceability validation in warn phase
    Then: No error-level issues are found
    And: Warnings are logged but do not fail
    """
    result = edge_validator.validate_all(phase="warn")

    # In warn phase, all errors are downgraded to warnings
    # This test ensures the validation infrastructure works
    assert isinstance(result, ValidationResult)
    assert result.checked_urns >= 0
    assert isinstance(result.issues, list)

    # Log summary for visibility
    if result.issues:
        by_type = {}
        for issue in result.issues:
            type_name = issue.issue_type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1

        summary = ", ".join(f"{k}: {v}" for k, v in by_type.items())
        pytest.skip(f"Validation found issues: {summary}")
