"""
Edge Validator
==============
Validates URN traceability graph for orphans, broken references, and completeness.

Pure graph consumer — receives a pre-built ``TraceabilityGraph`` and performs
all validation via node/edge queries.  Zero file I/O.

Detects:
- Orphaned URNs: Declared but not referenced (no incoming edges)
- Broken URNs: Referenced but not resolvable (target doesn't exist)
- Non-deterministic URNs: Resolve to multiple artifacts
- Missing required edges: Per Section 8 of URN spec

Severity levels:
- error: Must be fixed before merge
- warning: Should be reviewed, may be acceptable
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set
from enum import Enum

from atdd.coach.utils.graph.graph_builder import (
    TraceabilityGraph,
    EdgeType,
    URNNode,
)


class IssueSeverity(Enum):
    """Severity level for validation issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueType(Enum):
    """Types of validation issues."""

    ORPHAN = "orphan"  # URN declared but not referenced
    BROKEN = "broken"  # URN referenced but not resolvable
    NON_DETERMINISTIC = "non_deterministic"  # URN resolves to multiple artifacts
    MISSING_EDGE = "missing_edge"  # Required edge not present
    CYCLE = "cycle"  # Circular dependency detected
    INVALID_FORMAT = "invalid_format"  # URN format validation failure
    JEL_CONTRACT = "jel_contract"  # urn:jel:* contract ID (non-ATDD format)


@dataclass
class ValidationIssue:
    """
    A validation issue found in the traceability graph.

    Attributes:
        issue_type: Type of issue detected
        severity: Error, warning, or info
        urn: The URN involved in the issue
        message: Human-readable description
        location: File path where issue was found
        context: Additional context (e.g., referencing file)
        suggestion: Suggested fix
    """

    issue_type: IssueType
    severity: IssueSeverity
    urn: str
    message: str
    location: Optional[Path] = None
    context: Optional[str] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.issue_type.value,
            "severity": self.severity.value,
            "urn": self.urn,
            "message": self.message,
            "location": str(self.location) if self.location else None,
            "context": self.context,
            "suggestion": self.suggestion,
        }

    def __str__(self) -> str:
        """Human-readable string representation."""
        prefix = {
            IssueSeverity.ERROR: "ERROR",
            IssueSeverity.WARNING: "WARN",
            IssueSeverity.INFO: "INFO",
        }[self.severity]

        location_str = f" at {self.location}" if self.location else ""
        return f"[{prefix}] {self.issue_type.value}: {self.message}{location_str}"


@dataclass
class ValidationResult:
    """
    Aggregated result of all validation checks.

    Attributes:
        issues: List of all issues found
        checked_urns: Number of URNs validated
        families_checked: Families that were validated
    """

    issues: List[ValidationIssue] = field(default_factory=list)
    checked_urns: int = 0
    families_checked: List[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Check if any errors were found."""
        return any(i.severity == IssueSeverity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Check if any warnings were found."""
        return any(i.severity == IssueSeverity.WARNING for i in self.issues)

    @property
    def error_count(self) -> int:
        """Count of error-level issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of warning-level issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return not self.has_errors

    def filter_by_type(self, issue_type: IssueType) -> List[ValidationIssue]:
        """Get issues of a specific type."""
        return [i for i in self.issues if i.issue_type == issue_type]

    def filter_by_family(self, family: str) -> List[ValidationIssue]:
        """Get issues for a specific URN family."""
        return [i for i in self.issues if i.urn.startswith(f"{family}:")]

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "valid": self.is_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "checked_urns": self.checked_urns,
            "families_checked": self.families_checked,
            "issues": [i.to_dict() for i in self.issues],
        }


class EdgeValidator:
    """
    Validates URN traceability graph for completeness and correctness.

    Performs multiple validation passes:
    1. Orphan detection: URNs with no incoming references
    2. Broken reference detection: URNs that don't resolve
    3. Determinism validation: URNs should resolve to exactly one artifact
    4. Edge completeness: Required edges per spec Section 8
    """

    def __init__(self, graph: TraceabilityGraph):
        self.graph = graph

        # Families that are expected to have incoming edges (not orphaned)
        self._non_orphan_families = {"feature", "wmbt", "acc", "contract", "telemetry", "component"}

        # Families that are root nodes (allowed to be orphaned)
        self._root_families = {"wagon", "train"}

    def find_orphans(
        self, families: Optional[List[str]] = None
    ) -> List[ValidationIssue]:
        """
        Find orphaned URNs (declared but not referenced).

        Orphans are URNs that exist but have no incoming edges in the graph.
        Root families (wagon, train) are excluded as they're expected to be roots.

        Args:
            families: Families to check. If None, checks non-root families.

        Returns:
            List of orphan issues
        """
        issues = []
        target_families = set(families) if families else self._non_orphan_families

        for urn, node in self.graph.nodes.items():
            if node.family in self._root_families:
                continue
            if node.family not in target_families:
                continue

            incoming = self.graph.get_incoming_edges(urn)
            if not incoming:
                issues.append(
                    ValidationIssue(
                        issue_type=IssueType.ORPHAN,
                        severity=IssueSeverity.WARNING,
                        urn=urn,
                        message=f"Orphaned {node.family} URN: no parent references",
                        location=node.artifact_path,
                        context=f"Family: {node.family}",
                        suggestion=f"Add reference to this URN from a parent {self._suggest_parent(node.family)}",
                    )
                )

        return issues

    def _suggest_parent(self, family: str) -> str:
        """Suggest parent family for orphan fix."""
        parent_map = {
            "feature": "wagon",
            "wmbt": "wagon",
            "acc": "wmbt",
            "contract": "wagon",
            "telemetry": "wagon",
            "component": "feature",
        }
        return parent_map.get(family, "parent")

    def find_broken(
        self, families: Optional[List[str]] = None
    ) -> List[ValidationIssue]:
        """
        Find broken URN references (referenced but not resolvable).

        Broken URNs are referenced in the graph but don't resolve to
        any filesystem artifact.  Uses resolution metadata stored on
        each node by GraphBuilder.

        Args:
            families: Families to check. If None, checks all.

        Returns:
            List of broken reference issues
        """
        issues = []
        target_families = set(families) if families else None

        for urn, node in self.graph.nodes.items():
            if target_families and node.family not in target_families:
                continue

            if node.metadata.get("is_broken"):
                error = node.metadata.get("resolution_error") or "not resolvable"
                issues.append(
                    ValidationIssue(
                        issue_type=IssueType.BROKEN,
                        severity=IssueSeverity.ERROR,
                        urn=urn,
                        message=f"Broken URN: {error}",
                        location=None,
                        context=f"Family: {node.family}",
                        suggestion="Create the missing artifact or fix the URN",
                    )
                )

        return issues

    def validate_determinism(
        self, families: Optional[List[str]] = None
    ) -> List[ValidationIssue]:
        """
        Validate that URNs resolve deterministically (to exactly one artifact).

        Non-deterministic URNs are ambiguous and may cause issues in
        resolution and traceability.  Uses resolution metadata stored
        on each node by GraphBuilder.

        Args:
            families: Families to check. If None, checks all.

        Returns:
            List of non-determinism issues
        """
        issues = []
        target_families = set(families) if families else None

        for urn, node in self.graph.nodes.items():
            if target_families and node.family not in target_families:
                continue

            is_deterministic = node.metadata.get("is_deterministic", True)
            is_resolved = node.metadata.get("is_resolved", False)
            resolved_paths = node.metadata.get("resolved_paths", [])

            if not is_deterministic and is_resolved:
                paths_str = ", ".join(str(p) for p in resolved_paths[:3])
                if len(resolved_paths) > 3:
                    paths_str += f" (+{len(resolved_paths) - 3} more)"

                source_path = node.metadata.get("source_path")
                issues.append(
                    ValidationIssue(
                        issue_type=IssueType.NON_DETERMINISTIC,
                        severity=IssueSeverity.WARNING,
                        urn=urn,
                        message=f"URN resolves to {len(resolved_paths)} artifacts",
                        location=Path(source_path) if source_path else None,
                        context=f"Resolved to: {paths_str}",
                        suggestion="Ensure URN uniquely identifies one artifact",
                    )
                )

        return issues

    def validate_edges(
        self, families: Optional[List[str]] = None
    ) -> List[ValidationIssue]:
        """
        Validate required edges exist per spec Section 8.

        Required edge patterns:
        - wagon -> feature (contains)
        - wagon -> wmbt (contains)
        - wmbt -> acceptance (contains)
        - wagon -> contract (produces/consumes)
        - wagon -> telemetry (produces/consumes)
        - train -> wagon (includes)
        - feature -> component (contains) — chain completeness
        - component wagon slug -> wagon (ancestry validation)

        Args:
            families: Families to check. If None, checks all.

        Returns:
            List of missing edge issues
        """
        issues = []

        # Check that features have parent wagons
        for urn, node in self.graph.nodes.items():
            if node.family == "feature":
                parents = self.graph.get_parents(urn, EdgeType.CONTAINS)
                wagon_parents = [p for p in parents if p.family == "wagon"]
                if not wagon_parents:
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.MISSING_EDGE,
                            severity=IssueSeverity.WARNING,
                            urn=urn,
                            message="Feature has no parent wagon",
                            location=node.artifact_path,
                            suggestion="Add feature reference to wagon manifest",
                        )
                    )

                # Check feature has at least one component child
                component_children = [
                    c for c in self.graph.get_children(urn, EdgeType.CONTAINS)
                    if c.family == "component"
                ]
                if not component_children:
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.MISSING_EDGE,
                            severity=IssueSeverity.WARNING,
                            urn=urn,
                            message="Feature has no component children — chain dead-ends at feature level",
                            suggestion="Add at least one component:{wagon}:{feature}:* URN declaration",
                        )
                    )

            # Check that WMBTs have parent wagons
            elif node.family == "wmbt":
                parents = self.graph.get_parents(urn, EdgeType.CONTAINS)
                wagon_parents = [p for p in parents if p.family == "wagon"]
                if not wagon_parents:
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.MISSING_EDGE,
                            severity=IssueSeverity.WARNING,
                            urn=urn,
                            message="WMBT has no parent wagon",
                            location=node.artifact_path,
                            suggestion="Ensure WMBT is in correct wagon directory",
                        )
                    )

            # Check that acceptances have parent WMBTs
            elif node.family == "acc":
                parents = self.graph.get_parents(urn, EdgeType.CONTAINS)
                wmbt_parents = [p for p in parents if p.family == "wmbt"]
                if not wmbt_parents:
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.MISSING_EDGE,
                            severity=IssueSeverity.WARNING,
                            urn=urn,
                            message="Acceptance has no parent WMBT",
                            location=node.artifact_path,
                            suggestion="Ensure acceptance is declared in WMBT file",
                        )
                    )

            # Check that contracts have producing wagons
            elif node.family == "contract":
                incoming = self.graph.get_incoming_edges(urn)
                producer_edges = [
                    e for e in incoming
                    if e.edge_type == EdgeType.PRODUCES
                ]
                if not producer_edges:
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.MISSING_EDGE,
                            severity=IssueSeverity.WARNING,
                            urn=urn,
                            message="Contract has no producing wagon",
                            location=node.artifact_path,
                            suggestion="Add contract to wagon's produce[] section",
                        )
                    )

            # Check that telemetry has producing wagons
            elif node.family == "telemetry":
                incoming = self.graph.get_incoming_edges(urn)
                producer_edges = [
                    e for e in incoming
                    if e.edge_type == EdgeType.PRODUCES
                ]
                if not producer_edges:
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.MISSING_EDGE,
                            severity=IssueSeverity.WARNING,
                            urn=urn,
                            message="Telemetry has no producing wagon",
                            location=node.artifact_path,
                            suggestion="Add telemetry to wagon's produce[] section",
                        )
                    )

            # Check that trains have wagon references
            elif node.family == "train":
                outgoing = self.graph.get_outgoing_edges(urn)
                wagon_edges = [
                    e for e in outgoing
                    if e.edge_type == EdgeType.INCLUDES
                ]
                if not wagon_edges:
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.MISSING_EDGE,
                            severity=IssueSeverity.WARNING,
                            urn=urn,
                            message="Train has no wagon references",
                            location=node.artifact_path,
                            suggestion="Add wagons[] to train definition",
                        )
                    )

            elif node.family == "component":
                # Check component's wagon slug has a matching wagon node
                parts = urn.replace("component:", "").split(":")
                if len(parts) >= 2:
                    wagon_slug = parts[0]
                    expected_wagon = f"wagon:{wagon_slug}"
                    if not self.graph.get_node(expected_wagon):
                        issues.append(
                            ValidationIssue(
                                issue_type=IssueType.MISSING_EDGE,
                                severity=IssueSeverity.WARNING,
                                urn=urn,
                                message=f"Component wagon slug '{wagon_slug}' has no matching wagon:{wagon_slug} in graph",
                                location=node.artifact_path,
                                suggestion=f"Ensure wagon:{wagon_slug} exists, or use a valid wagon slug",
                            )
                        )

        return issues

    def validate_all(
        self, families: Optional[List[str]] = None, phase: str = "warn"
    ) -> ValidationResult:
        """
        Run all validation checks.

        Args:
            families: Families to check. If None, checks all.
            phase: Validation phase - "warn" or "fail"
                   "warn" reports errors as warnings
                   "fail" reports errors as errors

        Returns:
            Aggregated validation result
        """
        result = ValidationResult()

        # Derive families and URN count from the graph itself
        all_families: Set[str] = set()
        urn_count = 0
        for node in self.graph.nodes.values():
            all_families.add(node.family)
            if families is None or node.family in families:
                urn_count += 1
        result.families_checked = families or sorted(all_families)
        result.checked_urns = urn_count

        # Run all checks
        result.issues.extend(self.find_orphans(families))
        result.issues.extend(self.find_broken(families))
        result.issues.extend(self.validate_determinism(families))
        result.issues.extend(self.validate_edges(families))
        result.issues.extend(self.find_jel_contracts())

        # Adjust severity based on phase
        if phase == "warn":
            for issue in result.issues:
                if issue.severity == IssueSeverity.ERROR:
                    issue.severity = IssueSeverity.WARNING

        return result

    def validate_contracts(self) -> ValidationResult:
        """
        Specialized validation for contract URNs.

        Checks:
        - All contract schemas have producing wagon reference
        - All contract: URNs in produce[] resolve to files
        """
        result = ValidationResult()
        result.families_checked = ["contract"]

        contract_nodes = self.graph.nodes_by_family("contract")
        result.checked_urns = len(contract_nodes)

        for node in contract_nodes:
            # Skip synthetic JEL nodes — handled by find_jel_contracts
            if node.metadata.get("is_jel"):
                continue

            # Check if broken (from resolution metadata)
            if node.metadata.get("is_broken"):
                error = node.metadata.get("resolution_error") or "not resolvable"
                source_path = node.metadata.get("source_path")
                result.issues.append(
                    ValidationIssue(
                        issue_type=IssueType.BROKEN,
                        severity=IssueSeverity.ERROR,
                        urn=node.urn,
                        message=f"Contract URN broken: {error}",
                        location=Path(source_path) if source_path else None,
                    )
                )
                continue

            # Check for producer reference
            incoming = self.graph.get_incoming_edges(node.urn)
            producer_edges = [
                e for e in incoming if e.edge_type == EdgeType.PRODUCES
            ]

            if not producer_edges:
                source_path = node.metadata.get("source_path")
                result.issues.append(
                    ValidationIssue(
                        issue_type=IssueType.ORPHAN,
                        severity=IssueSeverity.WARNING,
                        urn=node.urn,
                        message="Contract has no producing wagon",
                        location=Path(source_path) if source_path else None,
                        suggestion="Add contract to wagon's produce[] section",
                    )
                )

        return result

    def find_jel_contracts(self) -> List[ValidationIssue]:
        """
        Find contract schemas with urn:jel:* IDs.

        Queries the graph for contract nodes tagged ``is_jel`` by
        GraphBuilder (zero file I/O).

        Returns:
            List of JEL contract issues with suggested fixes
        """
        issues = []

        for node in self.graph.nodes_by_family("contract"):
            if not node.metadata.get("is_jel"):
                continue

            schema_id = node.metadata.get("schema_id", "")
            correct_id = node.metadata.get("correct_id", "")

            issues.append(
                ValidationIssue(
                    issue_type=IssueType.JEL_CONTRACT,
                    severity=IssueSeverity.WARNING,
                    urn=node.urn,
                    message=f"Non-ATDD contract ID: {schema_id}",
                    location=node.artifact_path,
                    context=f"Current $id: {schema_id}",
                    suggestion=f"Change $id to: {correct_id}",
                )
            )

        return issues

    def fix_jel_contracts(self, dry_run: bool = False) -> List[Dict]:
        """
        Fix urn:jel:* contract IDs by deriving correct ID from file path.

        Uses graph metadata to identify JEL contracts, then performs
        targeted file writes (the only method that touches the filesystem).

        Args:
            dry_run: If True, only report what would be fixed without modifying files

        Returns:
            List of fix results with old_id, new_id, file_path, and status
        """
        import json
        import shutil

        fixes = []

        for node in self.graph.nodes_by_family("contract"):
            if not node.metadata.get("is_jel"):
                continue

            contract_file = node.artifact_path
            schema_id = node.metadata.get("schema_id", "")
            new_id = node.metadata.get("correct_id", "")

            if not contract_file or not Path(contract_file).exists():
                continue

            contract_file = Path(contract_file)

            fix_result = {
                "file_path": str(contract_file),
                "old_id": schema_id,
                "new_id": new_id,
                "status": "pending",
            }

            if dry_run:
                fix_result["status"] = "dry_run"
                fixes.append(fix_result)
                continue

            try:
                with open(contract_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Create backup
                backup_path = contract_file.with_suffix(".schema.json.bak")
                shutil.copy2(contract_file, backup_path)

                # Update the $id in the schema
                data["$id"] = new_id

                # Write back with preserved formatting (2-space indent)
                with open(contract_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.write("\n")  # Trailing newline

                fix_result["status"] = "fixed"
                fix_result["backup"] = str(backup_path)
                fixes.append(fix_result)

            except Exception as e:
                fixes.append({
                    "file_path": str(contract_file),
                    "old_id": schema_id,
                    "new_id": new_id,
                    "status": "error",
                    "error": str(e),
                })

        return fixes
