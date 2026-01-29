"""
Contract and telemetry traceability reconciliation command.

SPEC: .claude/agents/coach/utils.spec.yaml::traceability
IDs: SPEC-COACH-UTILS-0283 through SPEC-COACH-UTILS-0291

Purpose:
- Reconciles wagon manifests with actual contract/telemetry files
- Detects missing references (contract: null / telemetry: null)
- Proposes and applies fixes pragmatically with user approval
- Validates bidirectional traceability

Architecture: Clean 4-layer architecture
- Layer 1: Entities (Domain models)
- Layer 2: Use Cases (Business logic)
- Layer 3: Adapters (I/O, formatting)
- Layer 4: Command (CLI orchestration)
"""
from __future__ import annotations

import yaml
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
PLAN_DIR = REPO_ROOT / "plan"
CONTRACTS_DIR = REPO_ROOT / "contracts"
TELEMETRY_DIR = REPO_ROOT / "telemetry"
FACTS_DIR = REPO_ROOT / "facts"
FEATURES_DIR = REPO_ROOT / "features"


# ============================================================================
# LAYER 1: ENTITIES (Domain Models)
# ============================================================================


@dataclass
class ProduceItem:
    """
    A contract or telemetry item that a wagon produces.

    Domain entity representing the produce section of a wagon manifest.

    telemetry_ref supports:
    - List[str]: Array of telemetry URNs for multiple signals
    - None: No telemetry for this produce item
    """
    name: str
    to: str
    contract_ref: Optional[str]
    telemetry_ref: Optional[Union[str, List[str]]]
    wagon: str
    urn: Optional[str] = None  # Explicit URN from manifest (overrides derived URN)

    @property
    def has_null_contract_ref(self) -> bool:
        """Check if contract reference is null/missing."""
        return self.contract_ref is None or str(self.contract_ref) == 'None'

    @property
    def has_null_telemetry_ref(self) -> bool:
        """
        Check if telemetry reference is null/missing.

        Handles both single URN and array formats:
        - None -> True
        - Empty list -> True
        - Non-empty list -> False
        - String (legacy) -> False
        """
        if self.telemetry_ref is None:
            return True
        if isinstance(self.telemetry_ref, list):
            return len(self.telemetry_ref) == 0
        if isinstance(self.telemetry_ref, str):
            return self.telemetry_ref == 'None'
        return True

    @property
    def derived_contract_urn(self) -> str:
        """Derive contract URN from artifact name or use explicit URN."""
        # If explicit URN provided in manifest, use that
        if self.urn:
            return self.urn
        # Otherwise derive: Artifact name: match:dilemma.paired → contract:match:dilemma.paired
        return f"contract:{self.name}"

    @property
    def derived_telemetry_urn(self) -> str:
        """
        Derive telemetry URN from artifact name or use explicit URN.

        Returns artifact-level URN (complete with variant):
        - Artifact name: match:dilemma.paired → telemetry:match:dilemma.paired

        Note: This returns the complete URN now (not aspect-level).
        For array support, each variant gets its own complete URN.
        """
        # If explicit URN provided in manifest and it's a telemetry URN, use that
        if self.urn and self.urn.startswith('telemetry:'):
            return self.urn
        # Otherwise derive from name
        return f"telemetry:{self.name}"


@dataclass
class ContractFile:
    """
    A contract schema file in the contracts directory.

    Domain entity representing an actual contract file on disk.
    """
    file_path: str
    contract_id: str
    domain: str
    resource: str
    version: Optional[str]
    producer: Optional[str]
    consumers: List[str] = field(default_factory=list)
    traceability: Dict = field(default_factory=dict)


@dataclass
class TelemetryFile:
    """
    A telemetry definition file in the telemetry directory.

    Domain entity representing an actual telemetry file on disk.
    """
    file_path: str
    telemetry_id: str
    domain: str
    resource: str
    producer: Optional[str]
    artifact_ref: Optional[str] = None
    acceptance_criteria: List[str] = field(default_factory=list)


@dataclass
class SignalDeclaration:
    """
    A signal (metric/event/log) declared in an acceptance criteria.

    Domain entity representing telemetry requirements from acceptance.
    """
    wagon: str
    acceptance_urn: str
    signal_type: str  # metric, event, log
    signal_name: str
    plane: Optional[str] = None
    measure: Optional[str] = None


@dataclass
class FeatureIOSeed:
    """
    An I/O seed (consume/produce) declared in a feature file.

    Domain entity representing feature-level artifact dependencies.
    """
    name: str
    contract: Optional[str]
    telemetry: Optional[str]
    derived: Optional[bool] = None


@dataclass
class FeatureFile:
    """
    A feature YAML file with ioSeeds declarations.

    Domain entity representing an actual feature file on disk.
    """
    file_path: str
    feature_urn: str
    wagon_urn: str
    consume: List[FeatureIOSeed] = field(default_factory=list)
    produce: List[FeatureIOSeed] = field(default_factory=list)


@dataclass
class ReconciliationResult:
    """
    Result of reconciling wagon manifests with actual files.

    Aggregates all reconciliation findings.
    """
    total_issues: int = 0
    missing_contract_refs: List[Dict] = field(default_factory=list)
    missing_telemetry_refs: List[Dict] = field(default_factory=list)
    missing_signal_telemetry: List[Dict] = field(default_factory=list)
    orphaned_telemetry: List[Dict] = field(default_factory=list)
    telemetry_without_artifact_ref: List[Dict] = field(default_factory=list)
    telemetry_invalid_artifact_ref: List[Dict] = field(default_factory=list)
    telemetry_naming_violations: List[Dict] = field(default_factory=list)
    mismatched_producers: List[Dict] = field(default_factory=list)
    feature_io_mismatches: List[Dict] = field(default_factory=list)
    by_wagon: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class ContractImplementation:
    """
    A contract implementation in a specific programming language.

    Domain entity representing a DTO/entity class generated from a contract schema.
    """
    file_path: str
    contract_urn: str  # e.g., "match:dilemma.current"
    language: str  # 'python', 'dart', 'typescript'
    class_name: Optional[str] = None  # e.g., "CurrentDilemmaDTO"
    schema_ref: Optional[str] = None  # Path to source schema
    fields: List[str] = field(default_factory=list)
    urn_comment: Optional[str] = None  # Extracted from file header


@dataclass
class ImplementationCoverage:
    """
    Cross-language implementation status for a contract.

    Tracks which languages have implemented a given contract schema.
    """
    contract_urn: str
    schema_path: str
    python_impl: Optional[ContractImplementation] = None
    dart_impl: Optional[ContractImplementation] = None
    typescript_impl: Optional[ContractImplementation] = None

    @property
    def coverage_percentage(self) -> float:
        """Calculate percentage of target languages with implementations."""
        implemented = sum([
            self.python_impl is not None,
            self.dart_impl is not None,
            self.typescript_impl is not None
        ])
        return (implemented / 3.0) * 100

    @property
    def is_fully_covered(self) -> bool:
        """Check if all target languages have implementations."""
        return self.coverage_percentage == 100.0


@dataclass
class ImplementationReconciliationResult:
    """
    Result of reconciling contract schemas with language implementations.

    Aggregates all implementation coverage findings.
    """
    total_contracts: int = 0
    coverage_by_contract: List[ImplementationCoverage] = field(default_factory=list)
    missing_python: List[Dict] = field(default_factory=list)
    missing_dart: List[Dict] = field(default_factory=list)
    missing_typescript: List[Dict] = field(default_factory=list)
    orphaned_dtos: List[Dict] = field(default_factory=list)
    field_mismatches: List[Dict] = field(default_factory=list)

    @property
    def avg_coverage(self) -> float:
        """Calculate average coverage percentage across all contracts."""
        if not self.coverage_by_contract:
            return 0.0
        return sum(c.coverage_percentage for c in self.coverage_by_contract) / len(self.coverage_by_contract)

    @property
    def total_issues(self) -> int:
        """Count total implementation issues found."""
        return (
            len(self.missing_python) +
            len(self.missing_dart) +
            len(self.missing_typescript) +
            len(self.orphaned_dtos) +
            len(self.field_mismatches)
        )


@dataclass
class FunnelStage:
    """
    A stage in the traceability funnel with success/failure counts.

    Tracks how many items successfully pass through this stage.
    """
    stage_name: str  # e.g., "Wagon → Artifact"
    total_in: int  # Items entering this stage
    total_out: int  # Items successfully passing through
    leaks: List[Dict] = field(default_factory=list)  # Items that leaked (failed)

    @property
    def leak_rate(self) -> float:
        """Calculate percentage of items that leaked at this stage."""
        if self.total_in == 0:
            return 0.0
        return ((self.total_in - self.total_out) / self.total_in) * 100

    @property
    def pass_rate(self) -> float:
        """Calculate percentage of items that passed through."""
        if self.total_in == 0:
            return 0.0
        return (self.total_out / self.total_in) * 100


@dataclass
class ThemeFunnel:
    """
    Traceability funnel analysis for a theme (domain).

    Tracks: Theme → Wagons → Artifacts → Contracts → Implementations
    """
    theme: str  # e.g., "match", "scenario"
    wagon_count: int = 0
    artifact_count: int = 0
    contract_count: int = 0
    python_impl_count: int = 0
    dart_impl_count: int = 0
    typescript_impl_count: int = 0

    # Funnel stages
    stage_wagon_to_artifact: Optional[FunnelStage] = None
    stage_artifact_to_contract: Optional[FunnelStage] = None
    stage_contract_to_python: Optional[FunnelStage] = None
    stage_contract_to_dart: Optional[FunnelStage] = None
    stage_contract_to_typescript: Optional[FunnelStage] = None

    @property
    def overall_health(self) -> float:
        """Calculate overall traceability health (0-100%)."""
        if self.artifact_count == 0:
            return 0.0
        # Best case: artifact → contract → all 3 implementations
        max_possible = self.artifact_count * 3  # 3 languages per artifact
        actual = self.python_impl_count + self.dart_impl_count + self.typescript_impl_count
        return (actual / max_possible) * 100 if max_possible > 0 else 0.0


@dataclass
class SmartThemeFunnel:
    """
    Smart traceability funnel with producer/consumer awareness.

    Only counts required implementations based on actual wagon tech stacks.
    """
    theme: str
    wagon_count: int = 0
    artifact_count: int = 0
    contract_count: int = 0

    # Required (based on producer/consumer stacks)
    python_required: int = 0
    dart_required: int = 0
    typescript_required: int = 0

    # Implemented
    python_impl_count: int = 0
    dart_impl_count: int = 0
    typescript_impl_count: int = 0

    # Contract requirements details
    contracts: List[ContractRequirements] = field(default_factory=list)

    # Funnel stages
    stage_artifact_to_contract: Optional[FunnelStage] = None
    stage_contract_to_python: Optional[FunnelStage] = None
    stage_contract_to_dart: Optional[FunnelStage] = None
    stage_contract_to_typescript: Optional[FunnelStage] = None

    @property
    def overall_health(self) -> float:
        """Calculate health based on required vs implemented."""
        total_required = self.python_required + self.dart_required + self.typescript_required
        if total_required == 0:
            return 100.0  # No requirements = perfect health

        total_impl = self.python_impl_count + self.dart_impl_count + self.typescript_impl_count
        return (total_impl / total_required) * 100

    @property
    def python_missing_rate(self) -> float:
        """Calculate Python missing percentage."""
        if self.python_required == 0:
            return 0.0
        return ((self.python_required - self.python_impl_count) / self.python_required) * 100

    @property
    def dart_missing_rate(self) -> float:
        """Calculate Dart missing percentage."""
        if self.dart_required == 0:
            return 0.0
        return ((self.dart_required - self.dart_impl_count) / self.dart_required) * 100

    @property
    def typescript_missing_rate(self) -> float:
        """Calculate TypeScript missing percentage."""
        if self.typescript_required == 0:
            return 0.0
        return ((self.typescript_required - self.typescript_impl_count) / self.typescript_required) * 100


@dataclass
class FunnelAnalysisResult:
    """
    Complete funnel analysis showing traceability breakdown by theme.

    Identifies where in the chain (wagon→artifact→contract→impl) traceability breaks.
    """
    by_theme: Dict[str, ThemeFunnel] = field(default_factory=dict)
    orphaned_contracts: List[Dict] = field(default_factory=list)  # Contracts with no producing wagon

    @property
    def total_themes(self) -> int:
        """Count total themes analyzed."""
        return len(self.by_theme)

    @property
    def healthiest_theme(self) -> Optional[str]:
        """Identify theme with best traceability health."""
        if not self.by_theme:
            return None
        return max(self.by_theme.items(), key=lambda x: x[1].overall_health)[0]

    @property
    def sickest_theme(self) -> Optional[str]:
        """Identify theme with worst traceability health."""
        if not self.by_theme:
            return None
        return min(self.by_theme.items(), key=lambda x: x[1].overall_health)[0]


@dataclass
class SmartFunnelAnalysisResult:
    """
    Smart funnel analysis with producer/consumer awareness.

    Shows only required implementations, not all possible languages.
    """
    by_theme: Dict[str, SmartThemeFunnel] = field(default_factory=dict)

    @property
    def total_themes(self) -> int:
        """Count total themes analyzed."""
        return len(self.by_theme)

    @property
    def healthiest_theme(self) -> Optional[str]:
        """Identify theme with best traceability health."""
        if not self.by_theme:
            return None
        return max(self.by_theme.items(), key=lambda x: x[1].overall_health)[0]

    @property
    def sickest_theme(self) -> Optional[str]:
        """Identify theme with worst traceability health."""
        if not self.by_theme:
            return None
        return min(self.by_theme.items(), key=lambda x: x[1].overall_health)[0]


@dataclass
class WagonTechStack:
    """
    Technology stack information for a wagon.

    Determines which languages this wagon uses based on codebase structure.
    """
    wagon_urn: str  # e.g., "wagon:pace-dilemmas"
    wagon_slug: str  # e.g., "pace-dilemmas"
    has_python: bool = False
    has_dart: bool = False
    has_typescript: bool = False
    python_path: Optional[str] = None  # e.g., "python/pace_dilemmas/"
    dart_path: Optional[str] = None  # e.g., "lib/features/scenario/"
    typescript_path: Optional[str] = None  # e.g., "src/wagons/pace-dilemmas/"


@dataclass
class ContractRequirements:
    """
    Required DTO implementations for a contract based on producer/consumers.

    Only languages actually used by producer/consumers are marked as required.
    """
    contract_urn: str
    schema_path: str
    producer: Optional[str] = None  # wagon URN
    consumers: List[str] = field(default_factory=list)  # wagon URNs

    # Required implementations (based on tech stacks)
    requires_python: bool = False
    requires_dart: bool = False
    requires_typescript: bool = False

    # Actual implementations
    has_python: bool = False
    has_dart: bool = False
    has_typescript: bool = False

    # Missing requirements
    missing_python: bool = False
    missing_dart: bool = False
    missing_typescript: bool = False

    # Suggested paths
    python_path_suggestion: Optional[str] = None
    dart_path_suggestion: Optional[str] = None
    typescript_path_suggestion: Optional[str] = None

    def calculate_requirements(self, wagon_stacks: Dict[str, WagonTechStack]):
        """Calculate which languages are required based on producer/consumer stacks."""
        all_wagons = []
        if self.producer:
            all_wagons.append(self.producer)
        all_wagons.extend(self.consumers)

        for wagon_urn in all_wagons:
            stack = wagon_stacks.get(wagon_urn)
            if stack:
                if stack.has_python:
                    self.requires_python = True
                if stack.has_dart:
                    self.requires_dart = True
                if stack.has_typescript:
                    self.requires_typescript = True

        # Calculate missing
        self.missing_python = self.requires_python and not self.has_python
        self.missing_dart = self.requires_dart and not self.has_dart
        self.missing_typescript = self.requires_typescript and not self.has_typescript

    @property
    def total_required(self) -> int:
        """Count how many languages are required."""
        return sum([self.requires_python, self.requires_dart, self.requires_typescript])

    @property
    def total_implemented(self) -> int:
        """Count how many required languages are implemented."""
        implemented = 0
        if self.requires_python and self.has_python:
            implemented += 1
        if self.requires_dart and self.has_dart:
            implemented += 1
        if self.requires_typescript and self.has_typescript:
            implemented += 1
        return implemented

    @property
    def coverage_percentage(self) -> float:
        """Calculate coverage percentage (only counting required languages)."""
        if self.total_required == 0:
            return 100.0  # No requirements = 100% coverage
        return (self.total_implemented / self.total_required) * 100


# ============================================================================
# LAYER 2: USE CASES (Business Logic)
# ============================================================================


class ManifestParser:
    """
    Use case: Parse wagon manifests to extract produce items.

    Scans plan directory for wagon manifests and extracts produce declarations.
    """

    def __init__(self, plan_dir: Path = PLAN_DIR):
        self.plan_dir = plan_dir

    def parse_manifest(self, manifest_path: Path) -> Optional[Dict]:
        """Parse a single manifest file."""
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception:
            return None

    def parse_produce_items(self, manifest_data: Dict) -> List[ProduceItem]:
        """Extract produce items from manifest data."""
        produce_items = []
        wagon = manifest_data.get('wagon', 'unknown')

        for produce in manifest_data.get('produce', []):
            # Normalize telemetry to list for uniform processing
            telemetry_raw = produce.get('telemetry')
            telemetry_ref = self._normalize_telemetry_ref(telemetry_raw)

            item = ProduceItem(
                name=produce.get('name', ''),
                to=produce.get('to', ''),
                contract_ref=produce.get('contract'),
                telemetry_ref=telemetry_ref,
                wagon=wagon,
                urn=produce.get('urn')  # Extract explicit URN if provided
            )
            produce_items.append(item)

        return produce_items

    def _normalize_telemetry_ref(self, telemetry_raw):
        """
        Normalize telemetry reference to list format for uniform processing.

        Supports backward compatibility:
        - String URN -> [URN] (single-item list)
        - List of URNs -> List (unchanged)
        - None/null -> None

        Returns:
            List of URN strings, or None if telemetry is null
        """
        if telemetry_raw is None:
            return None
        elif isinstance(telemetry_raw, list):
            return telemetry_raw
        elif isinstance(telemetry_raw, str):
            return [telemetry_raw]
        else:
            return None

    def find_all_manifests(self) -> List[Tuple[Path, Dict]]:
        """Find and parse all wagon manifests."""
        manifests = []

        if not self.plan_dir.exists():
            return manifests

        for manifest_file in self.plan_dir.rglob("_*.yaml"):
            data = self.parse_manifest(manifest_file)
            if data and isinstance(data, dict):
                manifests.append((manifest_file, data))

        return manifests


class AcceptanceParser:
    """
    Use case: Parse acceptance criteria files to extract signal declarations.

    Finds and parses acceptance files to identify telemetry requirements.
    """

    def __init__(self, plan_dir: Path = PLAN_DIR):
        self.plan_dir = plan_dir

    def parse_acceptance_file(self, acceptance_file: Path) -> List[SignalDeclaration]:
        """Extract signal declarations from an acceptance file."""
        signals = []

        try:
            with open(acceptance_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except Exception:
            return signals

        wagon = data.get('metadata', {}).get('wagon', 'unknown')

        for acceptance in data.get('acceptances', []):
            acc_urn = acceptance.get('identity', {}).get('urn', '')
            signal_block = acceptance.get('signal', {})

            # Extract metrics
            for metric in signal_block.get('metrics', []):
                signals.append(SignalDeclaration(
                    wagon=wagon,
                    acceptance_urn=acc_urn,
                    signal_type='metric',
                    signal_name=metric.get('name', ''),
                    plane=metric.get('plane'),
                    measure=metric.get('type')
                ))

            # Extract events
            for event in signal_block.get('events', []):
                signals.append(SignalDeclaration(
                    wagon=wagon,
                    acceptance_urn=acc_urn,
                    signal_type='event',
                    signal_name=event.get('name', '')
                ))

            # Extract logs
            for log in signal_block.get('logs', []):
                signals.append(SignalDeclaration(
                    wagon=wagon,
                    acceptance_urn=acc_urn,
                    signal_type='log',
                    signal_name=log.get('body', '')[:50]  # First 50 chars as name
                ))

        return signals

    def find_all_acceptances(self) -> Dict[str, List[SignalDeclaration]]:
        """Find all acceptance files and extract signals grouped by wagon."""
        signals_by_wagon = defaultdict(list)

        if not self.plan_dir.exists():
            return signals_by_wagon

        # Pattern: plan/{wagon_dir}/*.yaml (excluding _*.yaml manifests)
        for wagon_dir in self.plan_dir.iterdir():
            if not wagon_dir.is_dir() or wagon_dir.name.startswith('_'):
                continue

            for acceptance_file in wagon_dir.glob('[CLPE]*.yaml'):
                signals = self.parse_acceptance_file(acceptance_file)
                wagon_name = wagon_dir.name.replace('_', '-')
                signals_by_wagon[wagon_name].extend(signals)

        return dict(signals_by_wagon)


class ContractFinder:
    """
    Use case: Find and match contract files with URNs.

    Scans contracts directory and provides intelligent URN matching.
    """

    def __init__(self, contracts_dir: Path = CONTRACTS_DIR):
        self.contracts_dir = contracts_dir

    def find_all_contracts(self) -> List[ContractFile]:
        """Find all contract schema files."""
        contracts = []

        if not self.contracts_dir.exists():
            return contracts

        for contract_file in self.contracts_dir.rglob("*.schema.json"):
            try:
                with open(contract_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                continue

            contract_id = data.get('$id', '')
            metadata = data.get('x-artifact-metadata', {})

            contract = ContractFile(
                file_path=str(contract_file.relative_to(REPO_ROOT)),
                contract_id=contract_id,
                domain=metadata.get('domain', ''),
                resource=metadata.get('resource', ''),
                version=metadata.get('version'),
                producer=metadata.get('producer'),
                consumers=metadata.get('consumers', []),
                traceability=metadata.get('traceability', {})
            )

            contracts.append(contract)

        return contracts

    def find_by_urn(self, urn: str, contracts: List[ContractFile]) -> Optional[ContractFile]:
        """
        Find a contract file matching a URN using multiple strategies.

        Tries:
        1. Exact match on contract_id
        2. Normalized match (colon vs dot variations)
        3. Path-based match
        """
        # Strip 'contract:' prefix if present
        search_urn = urn.replace('contract:', '')

        for contract in contracts:
            # Strategy 1: Exact match
            if contract.contract_id == search_urn:
                return contract

            # Strategy 2: Normalized match (colon vs dot)
            normalized_id = contract.contract_id.replace('.', ':')
            normalized_urn = search_urn.replace('.', ':')

            if normalized_id == normalized_urn:
                return contract

            # Strategy 3: Path-based match
            contract_path = contract.file_path.replace('contracts/', '').replace('.schema.json', '')
            urn_path = search_urn.replace(':', '/')

            if contract_path == urn_path:
                return contract

            # Also try with colon notation
            if contract_path.replace('/', ':') == normalized_urn:
                return contract

        return None


class FeatureFinder:
    """
    Use case: Find and parse feature files with ioSeeds.

    Scans plan/features and features/ directories for feature YAML files.
    """

    def __init__(self, plan_dir: Path = PLAN_DIR, features_dir: Path = FEATURES_DIR):
        self.plan_dir = plan_dir
        self.features_dir = features_dir

    def find_all_features(self) -> List[FeatureFile]:
        """Find all feature YAML files with ioSeeds."""
        features = []

        # Scan plan/*/features/*.yaml
        if self.plan_dir.exists():
            for feature_file in self.plan_dir.rglob("features/*.yaml"):
                feature = self.parse_feature_file(feature_file)
                if feature:
                    features.append(feature)

        # Scan features/*/*.yaml
        if self.features_dir.exists():
            for feature_file in self.features_dir.rglob("*.yaml"):
                if feature_file.name != '_features.yaml':
                    feature = self.parse_feature_file(feature_file)
                    if feature:
                        features.append(feature)

        return features

    def parse_feature_file(self, feature_path: Path) -> Optional[FeatureFile]:
        """Parse a feature YAML file and extract ioSeeds."""
        try:
            with open(feature_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        # Extract basic info
        feature_urn = data.get('urn', '')
        wagon_urn = data.get('wagon', '')

        # Extract ioSeeds
        io_seeds = data.get('ioSeeds', {})
        if not io_seeds:
            return None  # Skip features without ioSeeds

        consume_items = []
        for item in io_seeds.get('consume', []):
            consume_items.append(FeatureIOSeed(
                name=item.get('name', ''),
                contract=item.get('contract'),
                telemetry=item.get('telemetry'),
                derived=item.get('derived')
            ))

        produce_items = []
        for item in io_seeds.get('produce', []):
            produce_items.append(FeatureIOSeed(
                name=item.get('name', ''),
                contract=item.get('contract'),
                telemetry=item.get('telemetry'),
                derived=item.get('derived')
            ))

        return FeatureFile(
            file_path=str(feature_path.relative_to(REPO_ROOT)),
            feature_urn=feature_urn,
            wagon_urn=wagon_urn,
            consume=consume_items,
            produce=produce_items
        )


class TelemetryFinder:
    """
    Use case: Find and match telemetry files with URNs.

    Scans telemetry directory and provides intelligent URN matching.
    """

    def __init__(self, telemetry_dir: Path = TELEMETRY_DIR):
        self.telemetry_dir = telemetry_dir

    def find_all_telemetry(self) -> List[TelemetryFile]:
        """Find all telemetry definition files (JSON and YAML)."""
        telemetry_files = []

        if not self.telemetry_dir.exists():
            return telemetry_files

        # Scan for both .json (signal files) and .yaml (manifest files)
        import json
        for pattern in ["*.json", "*.yaml"]:
            for telemetry_file in self.telemetry_dir.rglob(pattern):
                # Skip test files
                if "/tests/" in str(telemetry_file):
                    continue

                try:
                    with open(telemetry_file, 'r', encoding='utf-8') as f:
                        if telemetry_file.suffix == '.json':
                            data = json.load(f)
                        else:
                            data = yaml.safe_load(f)
                except Exception:
                    continue

                # Extract telemetry ID from $id field or filename
                telemetry_id = data.get('$id') or data.get('id', '')

                telemetry = TelemetryFile(
                    file_path=str(telemetry_file.relative_to(REPO_ROOT)),
                    telemetry_id=telemetry_id,
                    domain=data.get('domain', ''),
                    resource=data.get('resource', ''),
                    producer=data.get('producer'),
                    artifact_ref=data.get('artifact_ref'),
                    acceptance_criteria=data.get('acceptance_criteria', [])
                )

                telemetry_files.append(telemetry)

        return telemetry_files


class WagonTechStackDetector:
    """
    Use case: Detect technology stack for each wagon.

    Scans codebase to determine which languages (Python/Dart/TS) each wagon uses.
    """

    def __init__(self, repo_root: Path = REPO_ROOT):
        self.repo_root = repo_root
        self.python_dir = repo_root / "python"
        self.dart_dir = repo_root / "lib"
        self.ts_dir = repo_root / "src"

    def detect_all_stacks(self) -> Dict[str, WagonTechStack]:
        """
        Detect tech stacks for all wagons.

        Returns:
            Dict mapping wagon URN to WagonTechStack
        """
        stacks = {}

        # Detect Python wagons
        if self.python_dir.exists():
            for wagon_dir in self.python_dir.iterdir():
                if wagon_dir.is_dir() and not wagon_dir.name.startswith(('_', '.')):
                    wagon_slug = wagon_dir.name
                    wagon_urn = f"wagon:{wagon_slug.replace('_', '-')}"

                    stack = WagonTechStack(
                        wagon_urn=wagon_urn,
                        wagon_slug=wagon_slug,
                        has_python=True,
                        python_path=str(wagon_dir.relative_to(self.repo_root))
                    )
                    stacks[wagon_urn] = stack

        # Detect Dart features (frontend)
        if self.dart_dir.exists():
            features_dir = self.dart_dir / "features"
            if features_dir.exists():
                for feature_dir in features_dir.iterdir():
                    if feature_dir.is_dir() and not feature_dir.name.startswith(('_', '.')):
                        feature_name = feature_dir.name
                        # Dart app acts as consumer, mapped by feature name
                        wagon_urn = f"app:dart:{feature_name}"

                        stack = WagonTechStack(
                            wagon_urn=wagon_urn,
                            wagon_slug=feature_name,
                            has_dart=True,
                            dart_path=str(feature_dir.relative_to(self.repo_root))
                        )
                        stacks[wagon_urn] = stack

        # Detect TypeScript wagons/features
        if self.ts_dir.exists():
            wagons_dir = self.ts_dir / "wagons"
            if wagons_dir.exists():
                for wagon_dir in wagons_dir.iterdir():
                    if wagon_dir.is_dir() and not wagon_dir.name.startswith(('_', '.')):
                        wagon_slug = wagon_dir.name
                        wagon_urn = f"wagon:{wagon_slug}"

                        # May already exist from Python detection
                        if wagon_urn in stacks:
                            stacks[wagon_urn].has_typescript = True
                            stacks[wagon_urn].typescript_path = str(wagon_dir.relative_to(self.repo_root))
                        else:
                            stack = WagonTechStack(
                                wagon_urn=wagon_urn,
                                wagon_slug=wagon_slug,
                                has_typescript=True,
                                typescript_path=str(wagon_dir.relative_to(self.repo_root))
                            )
                            stacks[wagon_urn] = stack

        return stacks


class PythonDTOFinder:
    """
    Use case: Find Python DTO implementations of contracts.

    Scans python/contracts/**/*.py for DTO classes with URN annotations.
    Pattern:
        # urn: contract:match:dilemma.current.dto
        @dataclass
        class CurrentDilemmaDTO:
    """

    # Pattern: # urn: contract:domain:resource[.variant][.dto]
    URN_PATTERN = re.compile(r'#\s*urn:\s*contract:([^:\s]+:[^\s]+)')
    # Alternative pattern: Contract: contracts/domain/resource.schema.json
    CONTRACT_PATH_PATTERN = re.compile(r'Contract:\s*contracts/([^/]+)/([^.\s]+)\.schema\.json')
    # Pattern: @dataclass (with optional args) followed by class XxxDTO
    DTO_CLASS_PATTERN = re.compile(r'@dataclass[^\n]*\nclass\s+(\w+(?:DTO)?)\s*[:\(]', re.MULTILINE)
    # Pattern: field_name: Type (simplified field extraction)
    FIELD_PATTERN = re.compile(r'^\s+(\w+):\s+', re.MULTILINE)

    def __init__(self, repo_root: Path = REPO_ROOT):
        self.repo_root = repo_root
        self.contracts_dir = repo_root / "python" / "contracts"

    def find_all_dtos(self) -> List[ContractImplementation]:
        """Scan python/contracts/ for DTO classes."""
        implementations = []

        if not self.contracts_dir.exists():
            return implementations

        for py_file in self.contracts_dir.rglob("*.py"):
            if py_file.name == '__init__.py':
                continue

            impl = self._parse_dto_file(py_file)
            if impl:
                implementations.append(impl)

        return implementations

    def _parse_dto_file(self, file_path: Path) -> Optional[ContractImplementation]:
        """Extract contract URN and DTO class from Python file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return None

        # Try primary pattern: # urn: contract:...
        urn_match = self.URN_PATTERN.search(content)
        if urn_match:
            urn_full = urn_match.group(1)
            # Remove .dto suffix if present for contract URN
            contract_urn = urn_full.replace('.dto', '')
        else:
            # Try alternative pattern: Contract: contracts/domain/resource.schema.json
            contract_match = self.CONTRACT_PATH_PATTERN.search(content)
            if not contract_match:
                return None

            # Reconstruct URN from file path
            domain = contract_match.group(1)
            resource = contract_match.group(2)
            contract_urn = f"{domain}:{resource}"
            urn_full = contract_urn

        # Extract DTO class name
        class_match = self.DTO_CLASS_PATTERN.search(content)
        class_name = class_match.group(1) if class_match else None

        # Extract field names (simplified)
        fields = self._extract_fields(content)

        # Derive schema path
        schema_ref = self._derive_schema_path(contract_urn)

        return ContractImplementation(
            file_path=str(file_path.relative_to(self.repo_root)),
            contract_urn=contract_urn,
            language='python',
            class_name=class_name,
            schema_ref=schema_ref,
            fields=fields,
            urn_comment=urn_full
        )

    def _extract_fields(self, content: str) -> List[str]:
        """Extract field names from dataclass."""
        fields = []
        in_class = False

        for line in content.split('\n'):
            # Detect class start
            if line.strip().startswith('class ') and 'DTO' in line:
                in_class = True
                continue

            if in_class:
                # Stop at next class or end of indentation
                if line and not line[0].isspace():
                    break

                # Match field pattern: field_name: Type
                match = self.FIELD_PATTERN.match(line)
                if match:
                    field_name = match.group(1)
                    # Skip dunder methods and properties
                    if not field_name.startswith('_'):
                        fields.append(field_name)

        return fields

    def _derive_schema_path(self, contract_urn: str) -> str:
        """Derive schema path from contract URN."""
        # contract:match:dilemma.current → contracts/match/dilemma/current.schema.json
        parts = contract_urn.split(':')
        if len(parts) >= 2:
            domain_resource = ':'.join(parts)
            path = domain_resource.replace(':', '/').replace('.', '/')
            return f"contracts/{path}.schema.json"
        return ""


class DartDTOFinder:
    """
    DEPRECATED: Dart/Flutter frontend was removed in SESSION-18.
    This class is kept for API compatibility but always returns empty results.
    """

    def __init__(self, repo_root: Path = REPO_ROOT):
        self.repo_root = repo_root

    def find_all_dtos(self) -> List[ContractImplementation]:
        """Returns empty - Dart frontend deprecated."""
        return []


class TypeScriptDTOFinder:
    """
    Use case: Find TypeScript interface/type definitions.

    Scans src/contracts/**/*.ts for contract interfaces.
    Pattern: export interface XxxDTO { ... }
    """

    INTERFACE_PATTERN = re.compile(r'export\s+(?:interface|type)\s+(\w+(?:DTO)?)\s*[{=]')
    FIELD_PATTERN = re.compile(r'^\s+(\w+)[\?:]:', re.MULTILINE)

    def __init__(self, repo_root: Path = REPO_ROOT):
        self.repo_root = repo_root
        self.src_dir = repo_root / "src"
        self.contracts_dir = repo_root / "contracts"

    def find_all_dtos(self) -> List[ContractImplementation]:
        """Scan TypeScript contract interfaces."""
        implementations = []

        # Check both src/ and contracts/ directories
        for base_dir in [self.src_dir, self.contracts_dir]:
            if not base_dir.exists():
                continue

            for ts_file in base_dir.rglob("*.ts"):
                # Skip test files
                if '.test.ts' in str(ts_file) or '.test.tsx' in str(ts_file):
                    continue

                impls = self._parse_ts_file(ts_file)
                implementations.extend(impls)

        return implementations

    def _parse_ts_file(self, file_path: Path) -> List[ContractImplementation]:
        """Extract interface/type definitions."""
        implementations = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return implementations

        # Find all exported interfaces/types
        for match in self.INTERFACE_PATTERN.finditer(content):
            interface_name = match.group(1)

            # Infer contract URN
            contract_urn = self._infer_contract_urn(file_path, interface_name)

            # Extract fields
            fields = self._extract_fields(content, interface_name, match.start())

            impl = ContractImplementation(
                file_path=str(file_path.relative_to(self.repo_root)),
                contract_urn=contract_urn,
                language='typescript',
                class_name=interface_name,
                schema_ref=self._derive_schema_path(contract_urn),
                fields=fields
            )
            implementations.append(impl)

        return implementations

    def _infer_contract_urn(self, file_path: Path, interface_name: str) -> str:
        """Infer contract URN from file path."""
        # Remove DTO suffix for URN
        base_name = interface_name.replace('DTO', '').replace('Interface', '')

        # Convert to kebab-case
        urn = self._camel_to_kebab(base_name)

        # Try to extract domain from path
        parts = file_path.parts
        if 'contracts' in parts:
            idx = parts.index('contracts')
            if idx + 1 < len(parts):
                # Use directory structure as URN
                path_parts = parts[idx + 1:]
                urn = ':'.join(path_parts).replace('.ts', '')

        return urn

    def _camel_to_kebab(self, name: str) -> str:
        """Convert CamelCase to kebab-case."""
        result = re.sub('([a-z0-9])([A-Z])', r'\1-\2', name)
        return result.lower()

    def _extract_fields(self, content: str, interface_name: str, start_pos: int) -> List[str]:
        """Extract field names from interface/type."""
        fields = []

        # Extract block after interface declaration
        snippet = content[start_pos:start_pos + 2000]

        # Find fields within braces
        brace_start = snippet.find('{')
        if brace_start == -1:
            return fields

        brace_count = 1
        brace_end = brace_start + 1

        # Find matching closing brace
        while brace_end < len(snippet) and brace_count > 0:
            if snippet[brace_end] == '{':
                brace_count += 1
            elif snippet[brace_end] == '}':
                brace_count -= 1
            brace_end += 1

        interface_body = snippet[brace_start:brace_end]

        for field_match in self.FIELD_PATTERN.finditer(interface_body):
            field_name = field_match.group(1)
            fields.append(field_name)

        return fields

    def _derive_schema_path(self, contract_urn: str) -> str:
        """Derive schema path from contract URN."""
        path = contract_urn.replace(':', '/').replace('.', '/')
        return f"contracts/{path}.schema.json"


class TraceabilityReconciler:
    """
    Use case: Reconcile wagon manifests with contracts/telemetry.

    Core business logic for detecting missing references and mismatches.
    """

    def __init__(self):
        self.manifest_parser = ManifestParser()
        self.acceptance_parser = AcceptanceParser()
        self.contract_finder = ContractFinder()
        self.telemetry_finder = TelemetryFinder()
        self.feature_finder = FeatureFinder()

    def parse_produce_items(self, manifest_data: Dict) -> List[ProduceItem]:
        """Parse produce items from manifest data."""
        return self.manifest_parser.parse_produce_items(manifest_data)

    def detect_missing_contract_refs(
        self,
        produce_items: List[ProduceItem],
        contracts: List[ContractFile]
    ) -> List[Dict]:
        """Detect produce items with null contract refs when contract files exist."""
        missing_refs = []

        for item in produce_items:
            if item.has_null_contract_ref:
                # Try to find matching contract using derived URN
                contract = self.contract_finder.find_by_urn(item.derived_contract_urn, contracts)

                if contract:
                    missing_refs.append({
                        'wagon': item.wagon,
                        'produce_name': item.name,
                        'urn': item.derived_contract_urn,
                        'proposed_fix': contract.file_path
                    })

        return missing_refs

    def detect_missing_telemetry_refs(
        self,
        produce_items: List[ProduceItem],
        telemetry_files: List[TelemetryFile]
    ) -> List[Dict]:
        """Detect produce items with null telemetry refs when telemetry files exist."""
        missing_refs = []

        for item in produce_items:
            if item.has_null_telemetry_ref:
                # Check if telemetry directory exists for this artifact using derived URN
                # Convention: telemetry URN is at aspect level (e.g., telemetry:match:dilemma)
                # Check if any telemetry files exist in the corresponding directory
                telemetry_urn = item.derived_telemetry_urn
                matching_telemetry = None
                for telemetry in telemetry_files:
                    # Match either exactly or as a prefix (for aspect-level matching)
                    if telemetry.telemetry_id == telemetry_urn or telemetry.telemetry_id.startswith(telemetry_urn):
                        matching_telemetry = telemetry
                        break

                if matching_telemetry:
                    missing_refs.append({
                        'wagon': item.wagon,
                        'produce_name': item.name,
                        'urn': telemetry_urn,
                        'proposed_fix': matching_telemetry.file_path
                    })

        return missing_refs

    def detect_signal_telemetry_issues(
        self,
        signals_by_wagon: Dict[str, List[SignalDeclaration]],
        telemetry_files: List[TelemetryFile],
        produce_items_by_wagon: Dict[str, List[ProduceItem]]
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Detect issues with signal-driven telemetry.

        Returns: (missing_signal_telemetry, orphaned_telemetry)
        """
        missing = []
        orphaned = []

        # Check wagons with signals
        for wagon, signals in signals_by_wagon.items():
            if not signals:
                continue

            # Wagon has signals - should have telemetry
            wagon_produce_items = produce_items_by_wagon.get(wagon, [])
            has_telemetry_ref = any(
                not item.has_null_telemetry_ref
                for item in wagon_produce_items
            )

            # Derive expected telemetry URN from first produce item
            if wagon_produce_items:
                expected_urn = wagon_produce_items[0].derived_telemetry_urn

                # Check if telemetry files exist
                has_telemetry_files = any(
                    expected_urn.replace('telemetry:', '') in telemetry.telemetry_id
                    for telemetry in telemetry_files
                )

                if has_telemetry_files and not has_telemetry_ref:
                    missing.append({
                        'wagon': wagon,
                        'signal_count': len(signals),
                        'expected_urn': expected_urn,
                        'current': 'telemetry: null',
                        'proposed_fix': expected_urn,
                        'reason': 'Acceptances declare signals, telemetry files exist, but wagon manifest has telemetry: null'
                    })

        # Check for orphaned telemetry (files exist but no signals in acceptances)
        # This is informational, not necessarily an error
        wagons_with_signals = set(signals_by_wagon.keys())
        wagons_with_telemetry = set()
        for telemetry in telemetry_files:
            # Extract wagon from telemetry_id (e.g., "match:dilemma" → "match")
            parts = telemetry.telemetry_id.split(':')
            if len(parts) >= 2:
                wagon_candidate = parts[0] if len(parts) == 2 else f"{parts[0]}-{parts[1]}"
                wagons_with_telemetry.add(wagon_candidate)

        # Orphaned = has telemetry but no signals
        for wagon in wagons_with_telemetry - wagons_with_signals:
            orphaned.append({
                'wagon': wagon,
                'note': 'Telemetry files exist but no signal declarations found in acceptances'
            })

        return missing, orphaned

    def validate_telemetry_artifact_refs(
        self,
        telemetry_files: List[TelemetryFile],
        contracts: List[ContractFile]
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Validate telemetry files reference valid artifacts/contracts.

        Returns: (missing_artifact_refs, invalid_artifact_refs)
        """
        missing = []
        invalid = []

        # Build contract URN lookup
        contract_urns = {contract.contract_id for contract in contracts}

        for telemetry in telemetry_files:
            # Skip manifest and pack files (not signal files)
            if (telemetry.file_path.endswith('_tracking.yaml') or
                telemetry.file_path.endswith('_signals.yaml') or
                '.pack.' in telemetry.file_path):
                continue

            # Check if artifact_ref is missing
            if not telemetry.artifact_ref:
                missing.append({
                    'telemetry_file': telemetry.file_path,
                    'telemetry_id': telemetry.telemetry_id,
                    'reason': 'Missing artifact_ref field (required per telemetry convention)'
                })
                continue

            # Check if artifact_ref points to valid contract
            # Remove 'contract:' prefix for matching
            artifact_ref_normalized = telemetry.artifact_ref.replace('contract:', '')

            # Check if contract exists
            contract_exists = any(
                artifact_ref_normalized in contract.contract_id or
                contract.contract_id in artifact_ref_normalized
                for contract in contracts
            )

            if not contract_exists:
                invalid.append({
                    'telemetry_file': telemetry.file_path,
                    'telemetry_id': telemetry.telemetry_id,
                    'artifact_ref': telemetry.artifact_ref,
                    'reason': f'References non-existent contract: {telemetry.artifact_ref}'
                })

        return missing, invalid

    def validate_telemetry_naming_convention(
        self,
        telemetry_files: List[TelemetryFile]
    ) -> List[Dict]:
        """
        Validate telemetry $id follows naming convention.

        Convention: {theme}:{domain}:{aspect}.{type}.{plane}[.{measure}]
        - Colons (:) for hierarchy (theme, domain, aspect)
        - Dots (.) for signal facets (type, plane, measure)

        Common violations:
        - Using colons for signal type: "match:pacing:exhausted:event" ❌
        - Should be dots: "match:pacing.exhausted.event.be" ✅
        """
        violations = []

        for telemetry in telemetry_files:
            if not telemetry.telemetry_id:
                continue

            telemetry_id = telemetry.telemetry_id

            # Skip manifest files (_tracking.yaml, _signals.yaml)
            if telemetry.file_path.endswith('_tracking.yaml') or \
               telemetry.file_path.endswith('_signals.yaml') or \
               '.pack.' in telemetry.file_path:
                continue

            # Check if ID contains signal facets (should have dots)
            # Valid pattern: has dots separating type.plane[.measure]
            has_dots = '.' in telemetry_id

            if not has_dots:
                violations.append({
                    'file': telemetry.file_path,
                    'current_id': telemetry_id,
                    'violation': 'Missing dots for signal facets (should have .type.plane)',
                    'example': 'Should be like: match:dilemma.current.metric.be.duration'
                })
                continue

            # Check for common violation: signal type using colon instead of dot
            # Pattern: ends with :event, :metric, :log, :trace (should be .event, .metric, etc)
            signal_types = ['event', 'metric', 'log', 'trace']
            for sig_type in signal_types:
                if f':{sig_type}' in telemetry_id and not f'.{sig_type}' in telemetry_id:
                    # Extract parts
                    parts = telemetry_id.split(':')

                    # Suggest fix by converting last colon to dot
                    suggested = telemetry_id.replace(f':{sig_type}', f'.{sig_type}')

                    violations.append({
                        'file': telemetry.file_path,
                        'current_id': telemetry_id,
                        'violation': f'Signal type ":{sig_type}" should use dot ".{sig_type}"',
                        'suggested_fix': suggested,
                        'reason': 'Colons are for hierarchy (theme:domain:aspect), dots are for signal facets (.type.plane.measure)'
                    })
                    break

            # Check artifact_ref matches ID hierarchy
            if telemetry.artifact_ref:
                # Extract artifact part (before first dot)
                artifact_hierarchy = telemetry_id.split('.')[0] if '.' in telemetry_id else telemetry_id
                artifact_ref_normalized = telemetry.artifact_ref.replace('contract:', '')

                # artifact_ref should match the hierarchy part
                # e.g., ID "match:pacing.exhausted.event.be" → artifact_ref "contract:match:pacing.exhausted"
                # But we need to account for the variant part (after .)
                if not artifact_ref_normalized.startswith(artifact_hierarchy.split('.')[0]):
                    violations.append({
                        'file': telemetry.file_path,
                        'current_id': telemetry_id,
                        'artifact_ref': telemetry.artifact_ref,
                        'violation': 'artifact_ref hierarchy does not match $id hierarchy',
                        'reason': f'$id starts with "{artifact_hierarchy}" but artifact_ref is "{telemetry.artifact_ref}"'
                    })

        return violations

    def validate_feature_wagon_io_alignment(
        self,
        features: List[FeatureFile],
        manifests: List[Tuple[Path, Dict]]
    ) -> List[Dict]:
        """
        Validate that feature ioSeeds align with wagon produce/consume.

        Checks:
        - Feature consume items must exist in wagon consume OR wagon produce (internal dependency)
        - Feature produce items must exist in wagon produce
        - Contract/telemetry URNs must match between feature and wagon
        """
        mismatches = []

        # Build wagon lookup
        wagon_by_urn = {}
        for manifest_path, manifest_data in manifests:
            wagon_slug = manifest_data.get('wagon', '')
            wagon_urn = f"wagon:{wagon_slug}"
            wagon_by_urn[wagon_urn] = {
                'slug': wagon_slug,
                'manifest_path': str(manifest_path.relative_to(REPO_ROOT)),
                'produce': manifest_data.get('produce', []),
                'consume': manifest_data.get('consume', [])
            }

        # Validate each feature
        for feature in features:
            wagon_data = wagon_by_urn.get(feature.wagon_urn)
            if not wagon_data:
                mismatches.append({
                    'feature': feature.feature_urn,
                    'file': feature.file_path,
                    'wagon': feature.wagon_urn,
                    'issue': f"Wagon not found: {feature.wagon_urn}"
                })
                continue

            # Build wagon artifact lookup by name
            wagon_artifacts = {}
            for item in wagon_data['produce']:
                wagon_artifacts[item['name']] = {
                    'type': 'produce',
                    'contract': item.get('contract'),
                    'telemetry': item.get('telemetry')
                }
            for item in wagon_data['consume']:
                wagon_artifacts[item['name']] = {
                    'type': 'consume',
                    'contract': item.get('contract'),
                    'telemetry': item.get('telemetry')
                }

            # Validate feature consume items
            for consume_item in feature.consume:
                if consume_item.name not in wagon_artifacts:
                    mismatches.append({
                        'feature': feature.feature_urn,
                        'file': feature.file_path,
                        'wagon': feature.wagon_urn,
                        'artifact_name': consume_item.name,
                        'issue': f"Feature consumes '{consume_item.name}' but wagon does not produce or consume it",
                        'feature_contract': consume_item.contract,
                        'feature_telemetry': consume_item.telemetry
                    })
                else:
                    # Check if contract URNs match
                    wagon_artifact = wagon_artifacts[consume_item.name]
                    if consume_item.contract != wagon_artifact['contract']:
                        mismatches.append({
                            'feature': feature.feature_urn,
                            'file': feature.file_path,
                            'wagon': feature.wagon_urn,
                            'artifact_name': consume_item.name,
                            'issue': f"Contract mismatch for '{consume_item.name}'",
                            'feature_contract': consume_item.contract,
                            'wagon_contract': wagon_artifact['contract']
                        })
                    # Check if telemetry URNs match
                    if consume_item.telemetry != wagon_artifact['telemetry']:
                        mismatches.append({
                            'feature': feature.feature_urn,
                            'file': feature.file_path,
                            'wagon': feature.wagon_urn,
                            'artifact_name': consume_item.name,
                            'issue': f"Telemetry mismatch for '{consume_item.name}'",
                            'feature_telemetry': consume_item.telemetry,
                            'wagon_telemetry': wagon_artifact['telemetry']
                        })

            # Validate feature produce items
            for produce_item in feature.produce:
                if produce_item.name not in wagon_artifacts:
                    mismatches.append({
                        'feature': feature.feature_urn,
                        'file': feature.file_path,
                        'wagon': feature.wagon_urn,
                        'artifact_name': produce_item.name,
                        'issue': f"Feature produces '{produce_item.name}' but wagon does not produce it",
                        'feature_contract': produce_item.contract,
                        'feature_telemetry': produce_item.telemetry
                    })
                else:
                    wagon_artifact = wagon_artifacts[produce_item.name]
                    if wagon_artifact['type'] != 'produce':
                        mismatches.append({
                            'feature': feature.feature_urn,
                            'file': feature.file_path,
                            'wagon': feature.wagon_urn,
                            'artifact_name': produce_item.name,
                            'issue': f"Feature produces '{produce_item.name}' but wagon only consumes it"
                        })
                    # Check if contract URNs match
                    if produce_item.contract != wagon_artifact['contract']:
                        mismatches.append({
                            'feature': feature.feature_urn,
                            'file': feature.file_path,
                            'wagon': feature.wagon_urn,
                            'artifact_name': produce_item.name,
                            'issue': f"Contract mismatch for '{produce_item.name}'",
                            'feature_contract': produce_item.contract,
                            'wagon_contract': wagon_artifact['contract']
                        })
                    # Check if telemetry URNs match
                    if produce_item.telemetry != wagon_artifact['telemetry']:
                        mismatches.append({
                            'feature': feature.feature_urn,
                            'file': feature.file_path,
                            'wagon': feature.wagon_urn,
                            'artifact_name': produce_item.name,
                            'issue': f"Telemetry mismatch for '{produce_item.name}'",
                            'feature_telemetry': produce_item.telemetry,
                            'wagon_telemetry': wagon_artifact['telemetry']
                        })

        return mismatches

    def reconcile_all(self) -> ReconciliationResult:
        """
        Run full repository reconciliation.

        Scans all wagon manifests and contract/telemetry files,
        detects issues, and generates comprehensive report.
        """
        result = ReconciliationResult()

        # Load all artifacts
        manifests = self.manifest_parser.find_all_manifests()
        contracts = self.contract_finder.find_all_contracts()
        telemetry_files = self.telemetry_finder.find_all_telemetry()
        signals_by_wagon = self.acceptance_parser.find_all_acceptances()

        # Build produce items by wagon for signal validation
        produce_items_by_wagon = {}

        # Process each wagon
        for manifest_path, manifest_data in manifests:
            wagon = manifest_data.get('wagon', 'unknown')
            produce_items = self.parse_produce_items(manifest_data)
            produce_items_by_wagon[wagon] = produce_items

            # Detect missing contract references
            missing_contracts = self.detect_missing_contract_refs(produce_items, contracts)
            result.missing_contract_refs.extend(missing_contracts)

            # Detect missing telemetry references
            missing_telemetry = self.detect_missing_telemetry_refs(produce_items, telemetry_files)
            result.missing_telemetry_refs.extend(missing_telemetry)

            # Group by wagon
            if wagon not in result.by_wagon:
                result.by_wagon[wagon] = {
                    'missing_contracts': [],
                    'missing_telemetry': [],
                    'missing_signal_telemetry': [],
                    'manifest_path': str(manifest_path.relative_to(REPO_ROOT))
                }

            result.by_wagon[wagon]['missing_contracts'].extend(missing_contracts)
            result.by_wagon[wagon]['missing_telemetry'].extend(missing_telemetry)

        # Detect signal-driven telemetry issues
        missing_signal_tel, orphaned_tel = self.detect_signal_telemetry_issues(
            signals_by_wagon, telemetry_files, produce_items_by_wagon
        )
        result.missing_signal_telemetry.extend(missing_signal_tel)
        result.orphaned_telemetry.extend(orphaned_tel)

        # Add signal issues to by_wagon grouping
        for issue in missing_signal_tel:
            wagon = issue['wagon']
            if wagon in result.by_wagon:
                result.by_wagon[wagon]['missing_signal_telemetry'].append(issue)

        # Validate telemetry → artifact references
        missing_artifact_refs, invalid_artifact_refs = self.validate_telemetry_artifact_refs(
            telemetry_files, contracts
        )
        result.telemetry_without_artifact_ref.extend(missing_artifact_refs)
        result.telemetry_invalid_artifact_ref.extend(invalid_artifact_refs)

        # Validate telemetry naming convention
        naming_violations = self.validate_telemetry_naming_convention(telemetry_files)
        result.telemetry_naming_violations.extend(naming_violations)

        # Validate feature-wagon I/O alignment
        features = self.feature_finder.find_all_features()
        feature_mismatches = self.validate_feature_wagon_io_alignment(features, manifests)
        result.feature_io_mismatches.extend(feature_mismatches)

        # Calculate total issues
        result.total_issues = (
            len(result.missing_contract_refs) +
            len(result.missing_telemetry_refs) +
            len(result.missing_signal_telemetry) +
            len(result.telemetry_without_artifact_ref) +
            len(result.telemetry_invalid_artifact_ref) +
            len(result.telemetry_naming_violations) +
            len(result.feature_io_mismatches)
        )

        return result


class ContractImplementationReconciler:
    """
    Use case: Reconcile contract schemas with multi-language implementations.

    Validates that each contract has implementations in target languages (Python, Dart, TS).
    Detects orphaned DTOs without schemas and missing implementations.
    """

    def __init__(self):
        self.contract_finder = ContractFinder()
        self.python_finder = PythonDTOFinder()
        self.dart_finder = DartDTOFinder()
        self.ts_finder = TypeScriptDTOFinder()

    def reconcile_all(self) -> ImplementationReconciliationResult:
        """
        Run full contract implementation reconciliation.

        Returns:
            ImplementationReconciliationResult with coverage analysis
        """
        result = ImplementationReconciliationResult()

        # Find all contracts and implementations
        contracts = self.contract_finder.find_all_contracts()
        py_dtos = self.python_finder.find_all_dtos()
        dart_dtos = self.dart_finder.find_all_dtos()
        ts_dtos = self.ts_finder.find_all_dtos()

        # Build lookup tables by contract URN
        py_by_urn = {}
        for dto in py_dtos:
            # Normalize URN (remove contract: prefix if present)
            urn = dto.contract_urn.replace('contract:', '')
            py_by_urn[urn] = dto

        dart_by_urn = {}
        for dto in dart_dtos:
            urn = dto.contract_urn.replace('contract:', '')
            dart_by_urn[urn] = dto

        ts_by_urn = {}
        for dto in ts_dtos:
            urn = dto.contract_urn.replace('contract:', '')
            ts_by_urn[urn] = dto

        # Build contract URN set for orphan detection
        contract_urns = set()
        for contract in contracts:
            urn = contract.contract_id.replace('contract:', '')
            contract_urns.add(urn)

        # Check each contract for implementation coverage
        for contract in contracts:
            urn = contract.contract_id.replace('contract:', '')

            # Find implementations for this contract
            python_impl = py_by_urn.get(urn)
            dart_impl = dart_by_urn.get(urn)
            ts_impl = ts_by_urn.get(urn)

            # Create coverage record
            coverage = ImplementationCoverage(
                contract_urn=urn,
                schema_path=contract.file_path,
                python_impl=python_impl,
                dart_impl=dart_impl,
                typescript_impl=ts_impl
            )

            result.coverage_by_contract.append(coverage)

            # Track missing implementations
            if not python_impl:
                result.missing_python.append({
                    'contract': urn,
                    'schema': contract.file_path,
                    'expected_path': self._suggest_python_path(urn)
                })

            if not dart_impl:
                result.missing_dart.append({
                    'contract': urn,
                    'schema': contract.file_path,
                    'expected_path': self._suggest_dart_path(urn)
                })

            if not ts_impl:
                result.missing_typescript.append({
                    'contract': urn,
                    'schema': contract.file_path,
                    'expected_path': self._suggest_ts_path(urn)
                })

        # Find orphaned DTOs (implementations without schemas)
        for dto in py_dtos + dart_dtos + ts_dtos:
            urn = dto.contract_urn.replace('contract:', '')

            # Normalize URN for matching (handle variations)
            urn_normalized = urn.replace('.', ':')
            matched = any(
                contract_urn.replace('.', ':') == urn_normalized
                for contract_urn in contract_urns
            )

            if not matched:
                result.orphaned_dtos.append({
                    'file': dto.file_path,
                    'urn': urn,
                    'language': dto.language,
                    'class_name': dto.class_name,
                    'reason': 'No corresponding schema file found'
                })

        # Set total contracts count
        result.total_contracts = len(contracts)

        return result

    def _suggest_python_path(self, contract_urn: str) -> str:
        """Suggest Python DTO path for a contract URN."""
        # match:dilemma.current → python/contracts/match/dilemma/current.py
        path = contract_urn.replace(':', '/').replace('.', '/')
        return f"python/contracts/{path}.py"

    def _suggest_dart_path(self, contract_urn: str) -> str:
        """Suggest Dart entity path for a contract URN."""
        # match:dilemma.current → lib/features/match/domain/dilemma_entities.dart
        parts = contract_urn.split(':')
        if len(parts) >= 2:
            domain = parts[0]
            resource = '_'.join(parts[1:]).replace('.', '_')
            return f"lib/features/{domain}/domain/{resource}_entities.dart"
        return f"lib/contracts/{contract_urn.replace(':', '/')}.dart"

    def _suggest_ts_path(self, contract_urn: str) -> str:
        """Suggest TypeScript interface path for a contract URN."""
        # match:dilemma.current → src/contracts/match/dilemma/current.ts
        path = contract_urn.replace(':', '/').replace('.', '/')
        return f"src/contracts/{path}.ts"


class SmartImplementationReconciler:
    """
    Use case: Smart reconciliation based on producer/consumer requirements.

    Only flags missing DTOs when producer/consumer wagons actually use that language.
    Maps wagon URN → feature → component → DTO path.
    """

    def __init__(self):
        self.contract_finder = ContractFinder()
        self.python_finder = PythonDTOFinder()
        self.dart_finder = DartDTOFinder()
        self.ts_finder = TypeScriptDTOFinder()
        self.stack_detector = WagonTechStackDetector()

    def reconcile_smart(self) -> List[ContractRequirements]:
        """
        Run smart reconciliation with producer/consumer awareness.

        Returns:
            List of ContractRequirements with smart coverage analysis
        """
        # Load all data
        contracts = self.contract_finder.find_all_contracts()
        py_dtos = self.python_finder.find_all_dtos()
        dart_dtos = self.dart_finder.find_all_dtos()
        ts_dtos = self.ts_finder.find_all_dtos()
        wagon_stacks = self.stack_detector.detect_all_stacks()

        # Build lookup tables
        py_by_urn = {dto.contract_urn.replace('contract:', ''): dto for dto in py_dtos}
        dart_by_urn = {dto.contract_urn.replace('contract:', ''): dto for dto in dart_dtos}
        ts_by_urn = {dto.contract_urn.replace('contract:', ''): dto for dto in ts_dtos}

        results = []

        for contract in contracts:
            urn = contract.contract_id.replace('contract:', '')

            # Create requirement
            req = ContractRequirements(
                contract_urn=urn,
                schema_path=contract.file_path,
                producer=contract.producer,
                consumers=contract.consumers
            )

            # Check actual implementations
            req.has_python = urn in py_by_urn
            req.has_dart = urn in dart_by_urn
            req.has_typescript = urn in ts_by_urn

            # Calculate requirements based on producer/consumer stacks
            req.calculate_requirements(wagon_stacks)

            # Generate path suggestions
            if req.missing_python:
                req.python_path_suggestion = self._suggest_python_path(urn, req.producer, wagon_stacks)

            if req.missing_dart:
                req.dart_path_suggestion = self._suggest_dart_path(urn, req.consumers, wagon_stacks)

            if req.missing_typescript:
                req.typescript_path_suggestion = self._suggest_ts_path(urn, req.producer, wagon_stacks)

            results.append(req)

        return results

    def _suggest_python_path(self, contract_urn: str, producer: Optional[str], wagon_stacks: Dict[str, WagonTechStack]) -> str:
        """Suggest Python DTO path based on producer wagon."""
        # Default path
        default_path = f"python/contracts/{contract_urn.replace(':', '/')}.py"

        if not producer:
            return default_path

        stack = wagon_stacks.get(producer)
        if stack and stack.python_path:
            # Suggest within wagon's directory
            return f"{stack.python_path}/contracts/{contract_urn.replace(':', '/')}.py"

        return default_path

    def _suggest_dart_path(self, contract_urn: str, consumers: List[str], wagon_stacks: Dict[str, WagonTechStack]) -> str:
        """Suggest Dart entity path based on consumer features."""
        # Check if any consumer is a Dart feature
        for consumer_urn in consumers:
            stack = wagon_stacks.get(consumer_urn)
            if stack and stack.has_dart and stack.dart_path:
                # Extract domain from contract URN
                domain = contract_urn.split(':')[0] if ':' in contract_urn else contract_urn
                entity_name = contract_urn.split(':')[-1].replace('.', '_')
                return f"{stack.dart_path}/domain/{entity_name}_entity.dart"

        # Default: try to match feature name from contract
        domain = contract_urn.split(':')[0] if ':' in contract_urn else contract_urn
        resource = contract_urn.split(':')[-1] if ':' in contract_urn else contract_urn
        return f"lib/features/{domain}/domain/{resource.replace('.', '_')}_entity.dart"

    def _suggest_ts_path(self, contract_urn: str, producer: Optional[str], wagon_stacks: Dict[str, WagonTechStack]) -> str:
        """Suggest TypeScript interface path based on producer wagon."""
        # Default path
        default_path = f"src/contracts/{contract_urn.replace(':', '/')}.ts"

        if not producer:
            return default_path

        stack = wagon_stacks.get(producer)
        if stack and stack.typescript_path:
            # Suggest within wagon's directory
            return f"{stack.typescript_path}/contracts/{contract_urn.replace(':', '/')}.ts"

        return default_path


class FunnelAnalyzer:
    """
    Use case: Analyze traceability funnel by theme.

    Identifies where traceability breaks: wagon → artifact → contract → impl.
    """

    def __init__(self):
        self.manifest_parser = ManifestParser()
        self.contract_finder = ContractFinder()
        self.python_finder = PythonDTOFinder()
        self.dart_finder = DartDTOFinder()
        self.ts_finder = TypeScriptDTOFinder()

    def analyze_funnel(self) -> FunnelAnalysisResult:
        """
        Run full funnel analysis.

        Returns:
            FunnelAnalysisResult with breakdown by theme
        """
        result = FunnelAnalysisResult()

        # Load all data
        manifests = self.manifest_parser.find_all_manifests()
        contracts = self.contract_finder.find_all_contracts()
        py_dtos = self.python_finder.find_all_dtos()
        dart_dtos = self.dart_finder.find_all_dtos()
        ts_dtos = self.ts_finder.find_all_dtos()

        # Build lookups
        contracts_by_urn = {
            c.contract_id.replace('contract:', ''): c
            for c in contracts
        }
        py_by_urn = {
            dto.contract_urn.replace('contract:', ''): dto
            for dto in py_dtos
        }
        dart_by_urn = {
            dto.contract_urn.replace('contract:', ''): dto
            for dto in dart_dtos
        }
        ts_by_urn = {
            dto.contract_urn.replace('contract:', ''): dto
            for dto in ts_dtos
        }

        # Extract all artifacts from wagon manifests
        artifacts_by_theme = defaultdict(list)
        wagons_by_theme = defaultdict(set)

        for manifest_path, manifest_data in manifests:
            wagon = manifest_data.get('wagon', 'unknown')

            for produce in manifest_data.get('produce', []):
                artifact_name = produce.get('name', '')
                if not artifact_name:
                    continue

                # Extract theme from artifact name (e.g., "match:dilemma.current" → "match")
                theme = artifact_name.split(':')[0] if ':' in artifact_name else 'unknown'

                artifacts_by_theme[theme].append({
                    'name': artifact_name,
                    'wagon': wagon,
                    'contract_ref': produce.get('contract'),
                    'has_contract': produce.get('contract') is not None and produce.get('contract') != 'null'
                })
                wagons_by_theme[theme].add(wagon)

        # Build funnel for each theme
        for theme in sorted(artifacts_by_theme.keys()):
            artifacts = artifacts_by_theme[theme]
            funnel = ThemeFunnel(theme=theme)

            # Count wagons for this theme
            funnel.wagon_count = len(wagons_by_theme[theme])

            # Count artifacts
            funnel.artifact_count = len(artifacts)

            # Artifact → Contract stage
            artifacts_with_contracts = [a for a in artifacts if a['has_contract']]
            artifact_to_contract_leaks = []

            for artifact in artifacts:
                if not artifact['has_contract']:
                    artifact_to_contract_leaks.append({
                        'artifact': artifact['name'],
                        'wagon': artifact['wagon'],
                        'reason': 'contract: null in wagon manifest'
                    })

            funnel.stage_artifact_to_contract = FunnelStage(
                stage_name="Artifact → Contract",
                total_in=len(artifacts),
                total_out=len(artifacts_with_contracts),
                leaks=artifact_to_contract_leaks
            )

            # Count contracts for this theme
            theme_contracts = [
                c for c in contracts
                if c.contract_id.startswith(theme + ':') or c.contract_id.startswith(theme + '.')
            ]
            funnel.contract_count = len(theme_contracts)

            # Contract → Python stage
            contract_to_python_leaks = []
            python_impl_count = 0

            for contract in theme_contracts:
                urn = contract.contract_id.replace('contract:', '')
                if urn in py_by_urn:
                    python_impl_count += 1
                else:
                    contract_to_python_leaks.append({
                        'contract': urn,
                        'schema': contract.file_path,
                        'reason': 'No Python DTO found'
                    })

            funnel.python_impl_count = python_impl_count
            funnel.stage_contract_to_python = FunnelStage(
                stage_name="Contract → Python",
                total_in=len(theme_contracts),
                total_out=python_impl_count,
                leaks=contract_to_python_leaks
            )

            # Contract → Dart stage
            contract_to_dart_leaks = []
            dart_impl_count = 0

            for contract in theme_contracts:
                urn = contract.contract_id.replace('contract:', '')
                if urn in dart_by_urn:
                    dart_impl_count += 1
                else:
                    contract_to_dart_leaks.append({
                        'contract': urn,
                        'schema': contract.file_path,
                        'reason': 'No Dart entity found'
                    })

            funnel.dart_impl_count = dart_impl_count
            funnel.stage_contract_to_dart = FunnelStage(
                stage_name="Contract → Dart",
                total_in=len(theme_contracts),
                total_out=dart_impl_count,
                leaks=contract_to_dart_leaks
            )

            # Contract → TypeScript stage
            contract_to_ts_leaks = []
            ts_impl_count = 0

            for contract in theme_contracts:
                urn = contract.contract_id.replace('contract:', '')
                if urn in ts_by_urn:
                    ts_impl_count += 1
                else:
                    contract_to_ts_leaks.append({
                        'contract': urn,
                        'schema': contract.file_path,
                        'reason': 'No TypeScript interface found'
                    })

            funnel.typescript_impl_count = ts_impl_count
            funnel.stage_contract_to_typescript = FunnelStage(
                stage_name="Contract → TypeScript",
                total_in=len(theme_contracts),
                total_out=ts_impl_count,
                leaks=contract_to_ts_leaks
            )

            result.by_theme[theme] = funnel

        # Find orphaned contracts (no producing wagon)
        all_artifact_names = set()
        for artifacts in artifacts_by_theme.values():
            for artifact in artifacts:
                all_artifact_names.add(artifact['name'])

        for contract in contracts:
            urn = contract.contract_id.replace('contract:', '')
            # Check if any artifact produces this contract
            if urn not in all_artifact_names:
                result.orphaned_contracts.append({
                    'contract': urn,
                    'schema': contract.file_path,
                    'producer': contract.producer
                })

        return result


class SmartFunnelAnalyzer:
    """
    Use case: Smart funnel analysis with producer/consumer awareness.

    Shows only required DTOs based on actual wagon tech stacks.
    """

    def __init__(self):
        self.manifest_parser = ManifestParser()
        self.smart_reconciler = SmartImplementationReconciler()

    def analyze_smart_funnel(self) -> SmartFunnelAnalysisResult:
        """
        Run smart funnel analysis.

        Returns:
            SmartFunnelAnalysisResult with producer/consumer aware breakdown
        """
        result = SmartFunnelAnalysisResult()

        # Get smart requirements (already has producer/consumer awareness)
        requirements = self.smart_reconciler.reconcile_smart()

        # Load manifests to get artifact info
        manifests = self.manifest_parser.find_all_manifests()

        # Build artifacts by theme
        artifacts_by_theme = defaultdict(list)
        wagons_by_theme = defaultdict(set)

        for manifest_path, manifest_data in manifests:
            wagon = manifest_data.get('wagon', 'unknown')

            for produce in manifest_data.get('produce', []):
                artifact_name = produce.get('name', '')
                if not artifact_name:
                    continue

                theme = artifact_name.split(':')[0] if ':' in artifact_name else 'unknown'

                artifacts_by_theme[theme].append({
                    'name': artifact_name,
                    'wagon': wagon,
                    'contract_ref': produce.get('contract'),
                    'has_contract': produce.get('contract') is not None and produce.get('contract') != 'null'
                })
                wagons_by_theme[theme].add(wagon)

        # Group requirements by theme
        requirements_by_theme = defaultdict(list)
        for req in requirements:
            theme = req.contract_urn.split(':')[0] if ':' in req.contract_urn else 'unknown'
            requirements_by_theme[theme].append(req)

        # Build smart funnel for each theme
        all_themes = set(list(artifacts_by_theme.keys()) + list(requirements_by_theme.keys()))

        for theme in sorted(all_themes):
            artifacts = artifacts_by_theme.get(theme, [])
            theme_requirements = requirements_by_theme.get(theme, [])

            funnel = SmartThemeFunnel(theme=theme)

            # Count wagons
            funnel.wagon_count = len(wagons_by_theme.get(theme, set()))

            # Count artifacts
            funnel.artifact_count = len(artifacts)

            # Count contracts
            funnel.contract_count = len(theme_requirements)

            # Store contract details
            funnel.contracts = theme_requirements

            # Calculate requirements and implementations
            funnel.python_required = sum(1 for r in theme_requirements if r.requires_python)
            funnel.dart_required = sum(1 for r in theme_requirements if r.requires_dart)
            funnel.typescript_required = sum(1 for r in theme_requirements if r.requires_typescript)

            funnel.python_impl_count = sum(1 for r in theme_requirements if r.requires_python and r.has_python)
            funnel.dart_impl_count = sum(1 for r in theme_requirements if r.requires_dart and r.has_dart)
            funnel.typescript_impl_count = sum(1 for r in theme_requirements if r.requires_typescript and r.has_typescript)

            # Artifact → Contract stage
            artifacts_with_contracts = [a for a in artifacts if a['has_contract']]
            artifact_to_contract_leaks = []

            for artifact in artifacts:
                if not artifact['has_contract']:
                    artifact_to_contract_leaks.append({
                        'artifact': artifact['name'],
                        'wagon': artifact['wagon'],
                        'reason': 'contract: null in wagon manifest'
                    })

            funnel.stage_artifact_to_contract = FunnelStage(
                stage_name="Artifact → Contract",
                total_in=len(artifacts),
                total_out=len(artifacts_with_contracts),
                leaks=artifact_to_contract_leaks
            )

            # Contract → Python stage (smart: only count if required)
            contract_to_python_leaks = []
            for req in theme_requirements:
                if req.requires_python and not req.has_python:
                    contract_to_python_leaks.append({
                        'contract': req.contract_urn,
                        'producer': req.producer,
                        'consumers': req.consumers,
                        'reason': 'Required by producer/consumer but not implemented'
                    })

            if funnel.python_required > 0:
                funnel.stage_contract_to_python = FunnelStage(
                    stage_name="Contract → Python (Required Only)",
                    total_in=funnel.python_required,
                    total_out=funnel.python_impl_count,
                    leaks=contract_to_python_leaks
                )

            # Contract → Dart stage (smart)
            contract_to_dart_leaks = []
            for req in theme_requirements:
                if req.requires_dart and not req.has_dart:
                    contract_to_dart_leaks.append({
                        'contract': req.contract_urn,
                        'producer': req.producer,
                        'consumers': req.consumers,
                        'reason': 'Required by Dart consumer but not implemented'
                    })

            if funnel.dart_required > 0:
                funnel.stage_contract_to_dart = FunnelStage(
                    stage_name="Contract → Dart (Required Only)",
                    total_in=funnel.dart_required,
                    total_out=funnel.dart_impl_count,
                    leaks=contract_to_dart_leaks
                )

            # Contract → TypeScript stage (smart)
            contract_to_ts_leaks = []
            for req in theme_requirements:
                if req.requires_typescript and not req.has_typescript:
                    contract_to_ts_leaks.append({
                        'contract': req.contract_urn,
                        'producer': req.producer,
                        'consumers': req.consumers,
                        'reason': 'Required by TypeScript consumer but not implemented'
                    })

            if funnel.typescript_required > 0:
                funnel.stage_contract_to_typescript = FunnelStage(
                    stage_name="Contract → TypeScript (Required Only)",
                    total_in=funnel.typescript_required,
                    total_out=funnel.typescript_impl_count,
                    leaks=contract_to_ts_leaks
                )

            result.by_theme[theme] = funnel

        return result


class TraceabilityValidator:
    """
    Use case: Validate bidirectional traceability.

    Ensures wagon->contract and contract->wagon references are consistent.
    """

    def validate_bidirectional(self, produce_item: Dict, contract: Dict) -> bool:
        """
        Validate bidirectional traceability.

        Checks:
        - Wagon declares producing the contract
        - Contract declares the wagon as producer
        """
        expected_producer = f"wagon:{produce_item['wagon']}"
        actual_producer = contract.get('producer')

        return expected_producer == actual_producer

    def check_producer_match(self, produce_item: Dict, contract: Dict) -> Optional[Dict]:
        """
        Check if producer in contract matches wagon declaration.

        Returns mismatch details if inconsistent, None if consistent.
        """
        expected_producer = f"wagon:{produce_item['wagon']}"
        actual_producer = contract.get('producer')

        if expected_producer != actual_producer:
            return {
                'wagon': produce_item['wagon'],
                'urn': produce_item['urn'],
                'expected': expected_producer,
                'actual': actual_producer,
                'contract_path': contract.get('file_path')
            }

        return None


class ContractMatcher:
    """
    Use case: Match contracts using multiple strategies.

    Wrapper around ContractFinder for backward compatibility.
    """

    def __init__(self):
        self.finder = ContractFinder()

    def find_by_urn(self, urn: str, contracts: List[Dict]) -> Optional[Dict]:
        """Find contract by URN using multiple matching strategies."""
        # Convert dict contracts to ContractFile objects
        contract_objs = [
            ContractFile(
                file_path=c['file_path'],
                contract_id=c.get('contract_id', ''),
                domain=c.get('domain', ''),
                resource=c.get('resource', ''),
                version=c.get('version'),
                producer=c.get('producer')
            )
            for c in contracts
        ]

        result = self.finder.find_by_urn(urn, contract_objs)

        if result:
            return {
                'file_path': result.file_path,
                'contract_id': result.contract_id
            }

        return None


# ============================================================================
# LAYER 3: ADAPTERS (I/O, Formatting)
# ============================================================================


class ReportFormatter:
    """
    Adapter: Format reconciliation reports for display.

    Converts reconciliation results into human-readable text.
    """

    @staticmethod
    def format_report(result: ReconciliationResult) -> str:
        """Format comprehensive reconciliation report."""
        lines = []

        lines.append("=" * 70)
        lines.append("CONTRACT/TELEMETRY TRACEABILITY RECONCILIATION")
        lines.append("=" * 70)
        lines.append("")

        # Summary
        lines.append(f"📊 SUMMARY")
        lines.append(f"   Total Issues: {result.total_issues}")
        lines.append(f"   Missing Contract Refs: {len(result.missing_contract_refs)}")
        lines.append(f"   Missing Telemetry Refs: {len(result.missing_telemetry_refs)}")
        lines.append(f"   Signal-Driven Telemetry Issues: {len(result.missing_signal_telemetry)}")
        lines.append(f"   Telemetry Without artifact_ref: {len(result.telemetry_without_artifact_ref)}")
        lines.append(f"   Telemetry With Invalid artifact_ref: {len(result.telemetry_invalid_artifact_ref)}")
        lines.append(f"   Telemetry Naming Convention Violations: {len(result.telemetry_naming_violations)}")
        lines.append(f"   Feature-Wagon I/O Mismatches: {len(result.feature_io_mismatches)}")
        if result.orphaned_telemetry:
            lines.append(f"   ℹ️  Orphaned Telemetry (info): {len(result.orphaned_telemetry)}")
        lines.append("")

        # Missing contract references
        if result.missing_contract_refs:
            lines.append("=" * 70)
            lines.append("🔴 MISSING CONTRACT REFERENCES")
            lines.append("=" * 70)
            lines.append("")

            for ref in result.missing_contract_refs:
                lines.append(f"Wagon: {ref['wagon']}")
                lines.append(f"  Produce: {ref['produce_name']}")
                lines.append(f"  URN: {ref['urn']}")
                lines.append(f"  Current: contract: null")
                lines.append(f"  💡 PROPOSED FIX: contract: {ref['proposed_fix']}")
                lines.append("")

        # Missing telemetry references
        if result.missing_telemetry_refs:
            lines.append("=" * 70)
            lines.append("🔴 MISSING TELEMETRY REFERENCES")
            lines.append("=" * 70)
            lines.append("")

            for ref in result.missing_telemetry_refs:
                lines.append(f"Wagon: {ref['wagon']}")
                lines.append(f"  Produce: {ref['produce_name']}")
                lines.append(f"  URN: {ref['urn']}")
                lines.append(f"  Current: telemetry: null")
                lines.append(f"  💡 PROPOSED FIX: telemetry: {ref['proposed_fix']}")
                lines.append("")

        # Signal-driven telemetry issues
        if result.missing_signal_telemetry:
            lines.append("=" * 70)
            lines.append("🔴 SIGNAL-DRIVEN TELEMETRY ISSUES")
            lines.append("=" * 70)
            lines.append("")

            for issue in result.missing_signal_telemetry:
                lines.append(f"Wagon: {issue['wagon']}")
                lines.append(f"  Signals Declared: {issue['signal_count']} (in acceptance criteria)")
                lines.append(f"  Expected URN: {issue['expected_urn']}")
                lines.append(f"  Current: {issue['current']}")
                lines.append(f"  💡 PROPOSED FIX: telemetry: {issue['proposed_fix']}")
                lines.append(f"  Reason: {issue['reason']}")
                lines.append("")

        # Telemetry without artifact_ref
        if result.telemetry_without_artifact_ref:
            lines.append("=" * 70)
            lines.append("🔴 TELEMETRY FILES WITHOUT artifact_ref")
            lines.append("=" * 70)
            lines.append("")

            for issue in result.telemetry_without_artifact_ref:
                lines.append(f"File: {issue['telemetry_file']}")
                lines.append(f"  ID: {issue['telemetry_id']}")
                lines.append(f"  Issue: {issue['reason']}")
                lines.append(f"  💡 FIX: Add artifact_ref field pointing to contract URN")
                lines.append("")

        # Telemetry with invalid artifact_ref
        if result.telemetry_invalid_artifact_ref:
            lines.append("=" * 70)
            lines.append("🔴 TELEMETRY FILES WITH INVALID artifact_ref")
            lines.append("=" * 70)
            lines.append("")

            for issue in result.telemetry_invalid_artifact_ref:
                lines.append(f"File: {issue['telemetry_file']}")
                lines.append(f"  ID: {issue['telemetry_id']}")
                lines.append(f"  artifact_ref: {issue['artifact_ref']}")
                lines.append(f"  Issue: {issue['reason']}")
                lines.append(f"  💡 FIX: Update artifact_ref to point to existing contract")
                lines.append("")

        # Telemetry naming convention violations
        if result.telemetry_naming_violations:
            lines.append("=" * 70)
            lines.append("🔴 TELEMETRY NAMING CONVENTION VIOLATIONS")
            lines.append("=" * 70)
            lines.append("")
            lines.append("Convention: {theme}:{domain}:{aspect}.{type}.{plane}[.{measure}]")
            lines.append("  - Colons (:) for hierarchy (theme, domain, aspect)")
            lines.append("  - Dots (.) for signal facets (type, plane, measure)")
            lines.append("")

            for violation in result.telemetry_naming_violations:
                lines.append(f"File: {violation['file']}")
                lines.append(f"  Current $id: {violation['current_id']}")
                lines.append(f"  Violation: {violation['violation']}")
                if 'suggested_fix' in violation:
                    lines.append(f"  💡 SUGGESTED FIX: $id = \"{violation['suggested_fix']}\"")
                if 'reason' in violation:
                    lines.append(f"  Reason: {violation['reason']}")
                if 'example' in violation:
                    lines.append(f"  Example: {violation['example']}")
                if 'artifact_ref' in violation:
                    lines.append(f"  artifact_ref: {violation['artifact_ref']}")
                lines.append("")

        # Feature-Wagon I/O Mismatches
        if result.feature_io_mismatches:
            lines.append("=" * 70)
            lines.append("🔴 FEATURE-WAGON I/O MISMATCHES")
            lines.append("=" * 70)
            lines.append("")
            lines.append("Features must align with their parent wagon's produce/consume declarations.")
            lines.append("")

            for mismatch in result.feature_io_mismatches:
                lines.append(f"Feature: {mismatch['feature']}")
                lines.append(f"  File: {mismatch['file']}")
                lines.append(f"  Wagon: {mismatch['wagon']}")
                if 'artifact_name' in mismatch:
                    lines.append(f"  Artifact: {mismatch['artifact_name']}")
                lines.append(f"  Issue: {mismatch['issue']}")

                # Show detailed mismatch information
                if 'feature_contract' in mismatch and 'wagon_contract' in mismatch:
                    lines.append(f"  Feature declares: contract: {mismatch['feature_contract']}")
                    lines.append(f"  Wagon declares:   contract: {mismatch['wagon_contract']}")
                elif 'feature_contract' in mismatch:
                    lines.append(f"  Feature contract: {mismatch['feature_contract']}")

                if 'feature_telemetry' in mismatch and 'wagon_telemetry' in mismatch:
                    lines.append(f"  Feature declares: telemetry: {mismatch['feature_telemetry']}")
                    lines.append(f"  Wagon declares:   telemetry: {mismatch['wagon_telemetry']}")
                elif 'feature_telemetry' in mismatch:
                    lines.append(f"  Feature telemetry: {mismatch['feature_telemetry']}")

                lines.append(f"  💡 FIX: Update feature ioSeeds to match wagon manifest declarations")
                lines.append("")

        # Orphaned telemetry (informational)
        if result.orphaned_telemetry:
            lines.append("=" * 70)
            lines.append("ℹ️  ORPHANED TELEMETRY (INFORMATIONAL)")
            lines.append("=" * 70)
            lines.append("")

            for orphan in result.orphaned_telemetry:
                lines.append(f"Wagon: {orphan['wagon']}")
                lines.append(f"  Note: {orphan['note']}")
                lines.append("")

        # By wagon summary
        if result.by_wagon:
            lines.append("=" * 70)
            lines.append("📦 BY WAGON")
            lines.append("=" * 70)
            lines.append("")

            for wagon, issues in result.by_wagon.items():
                total = (
                    len(issues['missing_contracts']) +
                    len(issues['missing_telemetry']) +
                    len(issues.get('missing_signal_telemetry', []))
                )
                if total > 0:
                    lines.append(f"🚂 {wagon}: {total} issues")
                    lines.append(f"   Manifest: {issues['manifest_path']}")
                    lines.append("")

        return "\n".join(lines)


class ImplementationReportFormatter:
    """
    Adapter: Format contract implementation coverage reports.

    Converts implementation reconciliation results into human-readable text.
    """

    @staticmethod
    def format_report(result: ImplementationReconciliationResult) -> str:
        """Format comprehensive implementation coverage report."""
        lines = []

        lines.append("=" * 80)
        lines.append("CONTRACT IMPLEMENTATION TRACEABILITY")
        lines.append("=" * 80)
        lines.append("")

        # Summary
        lines.append("📊 SUMMARY")
        lines.append(f"   Total Contracts: {result.total_contracts}")
        lines.append(f"   Average Coverage: {result.avg_coverage:.1f}%")
        lines.append(f"   Total Issues: {result.total_issues}")
        lines.append(f"   Missing Python DTOs: {len(result.missing_python)}")
        lines.append(f"   Missing Dart Entities: {len(result.missing_dart)}")
        lines.append(f"   Missing TypeScript Interfaces: {len(result.missing_typescript)}")
        lines.append(f"   Orphaned DTOs: {len(result.orphaned_dtos)}")
        lines.append("")

        # Coverage by contract
        if result.coverage_by_contract:
            lines.append("=" * 80)
            lines.append("📦 COVERAGE BY CONTRACT")
            lines.append("=" * 80)
            lines.append("")

            # Sort by coverage percentage (show incomplete first)
            sorted_coverage = sorted(result.coverage_by_contract, key=lambda c: c.coverage_percentage)

            for cov in sorted_coverage:
                # Status indicators
                status_py = "✅" if cov.python_impl else "❌"
                status_dart = "✅" if cov.dart_impl else "❌"
                status_ts = "✅" if cov.typescript_impl else "❌"

                coverage_emoji = "✅" if cov.is_fully_covered else "⚠️ "

                lines.append(f"{coverage_emoji} {cov.contract_urn} ({cov.coverage_percentage:.0f}%)")
                lines.append(f"  Schema: {cov.schema_path}")

                # Python implementation
                if cov.python_impl:
                    lines.append(f"  {status_py} Python: {cov.python_impl.file_path}")
                    lines.append(f"      Class: {cov.python_impl.class_name} ({len(cov.python_impl.fields)} fields)")
                else:
                    lines.append(f"  {status_py} Python: MISSING")

                # Dart implementation
                if cov.dart_impl:
                    lines.append(f"  {status_dart} Dart:   {cov.dart_impl.file_path}")
                    lines.append(f"      Class: {cov.dart_impl.class_name} ({len(cov.dart_impl.fields)} fields)")
                else:
                    lines.append(f"  {status_dart} Dart:   MISSING")

                # TypeScript implementation
                if cov.typescript_impl:
                    lines.append(f"  {status_ts} TypeScript: {cov.typescript_impl.file_path}")
                    lines.append(f"      Interface: {cov.typescript_impl.class_name} ({len(cov.typescript_impl.fields)} fields)")
                else:
                    lines.append(f"  {status_ts} TypeScript: MISSING")

                lines.append("")

        # Missing Python DTOs
        if result.missing_python:
            lines.append("=" * 80)
            lines.append("🔴 MISSING PYTHON DTOs")
            lines.append("=" * 80)
            lines.append("")

            for missing in result.missing_python:
                lines.append(f"Contract: {missing['contract']}")
                lines.append(f"  Schema: {missing['schema']}")
                lines.append(f"  💡 SUGGESTED: Create {missing['expected_path']}")
                lines.append("")

        # Missing Dart entities
        if result.missing_dart:
            lines.append("=" * 80)
            lines.append("🔴 MISSING DART ENTITIES")
            lines.append("=" * 80)
            lines.append("")

            for missing in result.missing_dart:
                lines.append(f"Contract: {missing['contract']}")
                lines.append(f"  Schema: {missing['schema']}")
                lines.append(f"  💡 SUGGESTED: Create {missing['expected_path']}")
                lines.append("")

        # Missing TypeScript interfaces
        if result.missing_typescript:
            lines.append("=" * 80)
            lines.append("🔴 MISSING TYPESCRIPT INTERFACES")
            lines.append("=" * 80)
            lines.append("")

            for missing in result.missing_typescript:
                lines.append(f"Contract: {missing['contract']}")
                lines.append(f"  Schema: {missing['schema']}")
                lines.append(f"  💡 SUGGESTED: Create {missing['expected_path']}")
                lines.append("")

        # Orphaned DTOs
        if result.orphaned_dtos:
            lines.append("=" * 80)
            lines.append("⚠️  ORPHANED DTOs (No Schema)")
            lines.append("=" * 80)
            lines.append("")

            for orphan in result.orphaned_dtos:
                lines.append(f"File: {orphan['file']}")
                lines.append(f"  URN: {orphan['urn']}")
                lines.append(f"  Language: {orphan['language'].capitalize()}")
                lines.append(f"  Class: {orphan['class_name']}")
                lines.append(f"  Issue: {orphan['reason']}")
                lines.append(f"  💡 FIX: Create schema at contracts/{orphan['urn'].replace(':', '/')}.schema.json")
                lines.append(f"         or remove orphaned DTO")
                lines.append("")

        # Statistics summary
        if result.coverage_by_contract:
            lines.append("=" * 80)
            lines.append("📈 STATISTICS")
            lines.append("=" * 80)
            lines.append("")

            # Count by coverage level
            full_coverage = sum(1 for c in result.coverage_by_contract if c.coverage_percentage == 100)
            partial_coverage = sum(1 for c in result.coverage_by_contract if 0 < c.coverage_percentage < 100)
            no_coverage = sum(1 for c in result.coverage_by_contract if c.coverage_percentage == 0)

            lines.append(f"Full Coverage (100%):    {full_coverage} contracts")
            lines.append(f"Partial Coverage:        {partial_coverage} contracts")
            lines.append(f"No Coverage (0%):        {no_coverage} contracts")
            lines.append("")

            # Language-specific stats
            total = len(result.coverage_by_contract)
            py_count = sum(1 for c in result.coverage_by_contract if c.python_impl)
            dart_count = sum(1 for c in result.coverage_by_contract if c.dart_impl)
            ts_count = sum(1 for c in result.coverage_by_contract if c.typescript_impl)

            lines.append(f"Python Implementation:   {py_count}/{total} ({py_count/total*100:.1f}%)")
            lines.append(f"Dart Implementation:     {dart_count}/{total} ({dart_count/total*100:.1f}%)")
            lines.append(f"TypeScript Implementation: {ts_count}/{total} ({ts_count/total*100:.1f}%)")
            lines.append("")

        return "\n".join(lines)


class FunnelReportFormatter:
    """
    Adapter: Format funnel analysis reports.

    Shows traceability breakdown by theme with leak identification.
    """

    @staticmethod
    def format_report(result: FunnelAnalysisResult) -> str:
        """Format comprehensive funnel analysis report."""
        lines = []

        lines.append("=" * 80)
        lines.append("TRACEABILITY FUNNEL ANALYSIS")
        lines.append("=" * 80)
        lines.append("")

        # Executive summary
        lines.append("📊 EXECUTIVE SUMMARY")
        lines.append(f"   Total Themes: {result.total_themes}")
        if result.healthiest_theme:
            lines.append(f"   🏆 Healthiest Theme: {result.healthiest_theme}")
        if result.sickest_theme:
            lines.append(f"   ⚠️  Sickest Theme: {result.sickest_theme}")
        lines.append("")

        # Funnel by theme
        for theme, funnel in sorted(result.by_theme.items(),
                                     key=lambda x: x[1].overall_health,
                                     reverse=True):
            lines.append("=" * 80)
            health_emoji = "✅" if funnel.overall_health >= 75 else "⚠️ " if funnel.overall_health >= 25 else "🔴"
            lines.append(f"{health_emoji} THEME: {theme.upper()} (Health: {funnel.overall_health:.1f}%)")
            lines.append("=" * 80)
            lines.append("")

            # Funnel visualization
            lines.append("FUNNEL STAGES:")
            lines.append("")
            lines.append(f"  ┌─ Wagons: {funnel.wagon_count}")
            lines.append(f"  │")
            lines.append(f"  ├─ Artifacts: {funnel.artifact_count}")

            if funnel.stage_artifact_to_contract:
                stage = funnel.stage_artifact_to_contract
                leak_indicator = "💧" if stage.leak_rate > 0 else "  "
                lines.append(f"  │  {leak_indicator} ({stage.pass_rate:.0f}% pass, {stage.leak_rate:.0f}% leak)")

            lines.append(f"  │")
            lines.append(f"  ├─ Contracts: {funnel.contract_count}")
            lines.append(f"  │")

            # Python branch
            if funnel.stage_contract_to_python:
                stage = funnel.stage_contract_to_python
                leak_indicator = "💧" if stage.leak_rate > 0 else "  "
                lines.append(f"  ├──┬─ Python DTOs: {funnel.python_impl_count}")
                lines.append(f"  │  {leak_indicator}  ({stage.pass_rate:.0f}% pass, {stage.leak_rate:.0f}% leak)")

            # Dart branch
            if funnel.stage_contract_to_dart:
                stage = funnel.stage_contract_to_dart
                leak_indicator = "💧" if stage.leak_rate > 0 else "  "
                lines.append(f"  ├──┬─ Dart Entities: {funnel.dart_impl_count}")
                lines.append(f"  │  {leak_indicator}  ({stage.pass_rate:.0f}% pass, {stage.leak_rate:.0f}% leak)")

            # TypeScript branch
            if funnel.stage_contract_to_typescript:
                stage = funnel.stage_contract_to_typescript
                leak_indicator = "💧" if stage.leak_rate > 0 else "  "
                lines.append(f"  └──┬─ TypeScript Interfaces: {funnel.typescript_impl_count}")
                lines.append(f"     {leak_indicator}  ({stage.pass_rate:.0f}% pass, {stage.leak_rate:.0f}% leak)")

            lines.append("")

            # Show leaks for this theme
            if funnel.stage_artifact_to_contract and funnel.stage_artifact_to_contract.leaks:
                lines.append("  💧 LEAKS AT ARTIFACT → CONTRACT:")
                for leak in funnel.stage_artifact_to_contract.leaks[:5]:  # Show first 5
                    lines.append(f"     - {leak['artifact']} (wagon: {leak['wagon']})")
                if len(funnel.stage_artifact_to_contract.leaks) > 5:
                    lines.append(f"     ... and {len(funnel.stage_artifact_to_contract.leaks) - 5} more")
                lines.append("")

            if funnel.stage_contract_to_python and funnel.stage_contract_to_python.leaks:
                lines.append("  💧 LEAKS AT CONTRACT → PYTHON:")
                for leak in funnel.stage_contract_to_python.leaks[:5]:
                    lines.append(f"     - {leak['contract']}")
                if len(funnel.stage_contract_to_python.leaks) > 5:
                    lines.append(f"     ... and {len(funnel.stage_contract_to_python.leaks) - 5} more")
                lines.append("")

            if funnel.stage_contract_to_dart and funnel.stage_contract_to_dart.leaks:
                lines.append("  💧 LEAKS AT CONTRACT → DART:")
                for leak in funnel.stage_contract_to_dart.leaks[:5]:
                    lines.append(f"     - {leak['contract']}")
                if len(funnel.stage_contract_to_dart.leaks) > 5:
                    lines.append(f"     ... and {len(funnel.stage_contract_to_dart.leaks) - 5} more")
                lines.append("")

        # Orphaned contracts
        if result.orphaned_contracts:
            lines.append("=" * 80)
            lines.append("⚠️  ORPHANED CONTRACTS (No Producing Wagon)")
            lines.append("=" * 80)
            lines.append("")

            for orphan in result.orphaned_contracts[:10]:
                lines.append(f"  - {orphan['contract']}")
                lines.append(f"    Schema: {orphan['schema']}")
                lines.append(f"    Producer: {orphan.get('producer', 'unknown')}")
                lines.append("")

            if len(result.orphaned_contracts) > 10:
                lines.append(f"  ... and {len(result.orphaned_contracts) - 10} more orphaned contracts")
                lines.append("")

        # Key insights
        lines.append("=" * 80)
        lines.append("💡 KEY INSIGHTS")
        lines.append("=" * 80)
        lines.append("")

        # Find worst leaks
        worst_artifact_leak = None
        worst_python_leak = None
        worst_dart_leak = None

        for theme, funnel in result.by_theme.items():
            if funnel.stage_artifact_to_contract and funnel.stage_artifact_to_contract.leak_rate > 0:
                if not worst_artifact_leak or funnel.stage_artifact_to_contract.leak_rate > worst_artifact_leak[1]:
                    worst_artifact_leak = (theme, funnel.stage_artifact_to_contract.leak_rate)

            if funnel.stage_contract_to_python and funnel.stage_contract_to_python.leak_rate > 0:
                if not worst_python_leak or funnel.stage_contract_to_python.leak_rate > worst_python_leak[1]:
                    worst_python_leak = (theme, funnel.stage_contract_to_python.leak_rate)

            if funnel.stage_contract_to_dart and funnel.stage_contract_to_dart.leak_rate > 0:
                if not worst_dart_leak or funnel.stage_contract_to_dart.leak_rate > worst_dart_leak[1]:
                    worst_dart_leak = (theme, funnel.stage_contract_to_dart.leak_rate)

        if worst_artifact_leak:
            lines.append(f"⚠️  Biggest Artifact→Contract leak: '{worst_artifact_leak[0]}' ({worst_artifact_leak[1]:.0f}% leak)")

        if worst_python_leak:
            lines.append(f"⚠️  Biggest Contract→Python leak: '{worst_python_leak[0]}' ({worst_python_leak[1]:.0f}% leak)")

        if worst_dart_leak:
            lines.append(f"⚠️  Biggest Contract→Dart leak: '{worst_dart_leak[0]}' ({worst_dart_leak[1]:.0f}% leak)")

        lines.append("")
        lines.append("💡 Focus on fixing the biggest leaks first for maximum impact!")
        lines.append("")

        return "\n".join(lines)


class SmartFunnelReportFormatter:
    """
    Adapter: Format smart funnel reports with producer/consumer awareness.

    Shows visual funnel with only required DTOs.
    """

    @staticmethod
    def format_report(result: SmartFunnelAnalysisResult) -> str:
        """Format smart funnel analysis report."""
        lines = []

        lines.append("=" * 80)
        lines.append("SMART TRACEABILITY FUNNEL (Producer/Consumer Aware)")
        lines.append("=" * 80)
        lines.append("")

        # Executive summary
        lines.append("📊 EXECUTIVE SUMMARY")
        lines.append(f"   Total Themes: {result.total_themes}")
        if result.healthiest_theme:
            lines.append(f"   🏆 Healthiest Theme: {result.healthiest_theme}")
        if result.sickest_theme:
            lines.append(f"   ⚠️  Sickest Theme: {result.sickest_theme}")
        lines.append("")

        # Funnel by theme (sorted by health, worst first)
        for theme, funnel in sorted(result.by_theme.items(),
                                     key=lambda x: x[1].overall_health):
            lines.append("=" * 80)
            health_emoji = "✅" if funnel.overall_health >= 75 else "⚠️ " if funnel.overall_health >= 25 else "🔴"
            lines.append(f"{health_emoji} THEME: {theme.upper()} (Health: {funnel.overall_health:.1f}%)")
            lines.append("=" * 80)
            lines.append("")

            # Funnel visualization
            lines.append("FUNNEL STAGES:")
            lines.append("")
            lines.append(f"  ┌─ Wagons: {funnel.wagon_count}")
            lines.append(f"  │")
            lines.append(f"  ├─ Artifacts: {funnel.artifact_count}")

            if funnel.stage_artifact_to_contract:
                stage = funnel.stage_artifact_to_contract
                leak_indicator = "💧" if stage.leak_rate > 0 else "  "
                lines.append(f"  │  {leak_indicator} ({stage.pass_rate:.0f}% pass, {stage.leak_rate:.0f}% leak)")

            lines.append(f"  │")
            lines.append(f"  ├─ Contracts: {funnel.contract_count}")
            lines.append(f"  │")

            # Python branch (only if required)
            if funnel.python_required > 0:
                leak_indicator = "💧" if funnel.python_impl_count < funnel.python_required else "  "
                lines.append(f"  ├──┬─ Python DTOs: {funnel.python_impl_count}/{funnel.python_required} required")
                if funnel.stage_contract_to_python:
                    lines.append(f"  │  {leak_indicator}  ({funnel.stage_contract_to_python.pass_rate:.0f}% pass, {funnel.stage_contract_to_python.leak_rate:.0f}% leak)")
            else:
                lines.append(f"  ├──┬─ Python DTOs: Not required")

            # Dart branch (only if required)
            if funnel.dart_required > 0:
                leak_indicator = "💧" if funnel.dart_impl_count < funnel.dart_required else "  "
                lines.append(f"  ├──┬─ Dart Entities: {funnel.dart_impl_count}/{funnel.dart_required} required")
                if funnel.stage_contract_to_dart:
                    lines.append(f"  │  {leak_indicator}  ({funnel.stage_contract_to_dart.pass_rate:.0f}% pass, {funnel.stage_contract_to_dart.leak_rate:.0f}% leak)")
            else:
                lines.append(f"  ├──┬─ Dart Entities: Not required")

            # TypeScript branch (only if required)
            if funnel.typescript_required > 0:
                leak_indicator = "💧" if funnel.typescript_impl_count < funnel.typescript_required else "  "
                lines.append(f"  └──┬─ TypeScript Interfaces: {funnel.typescript_impl_count}/{funnel.typescript_required} required")
                if funnel.stage_contract_to_typescript:
                    lines.append(f"     {leak_indicator}  ({funnel.stage_contract_to_typescript.pass_rate:.0f}% pass, {funnel.stage_contract_to_typescript.leak_rate:.0f}% leak)")
            else:
                lines.append(f"  └──┬─ TypeScript Interfaces: Not required")

            lines.append("")

            # Show leaks
            if funnel.stage_artifact_to_contract and funnel.stage_artifact_to_contract.leaks:
                lines.append("  💧 LEAKS AT ARTIFACT → CONTRACT:")
                for leak in funnel.stage_artifact_to_contract.leaks[:5]:
                    lines.append(f"     - {leak['artifact']} (wagon: {leak['wagon']})")
                if len(funnel.stage_artifact_to_contract.leaks) > 5:
                    lines.append(f"     ... and {len(funnel.stage_artifact_to_contract.leaks) - 5} more")
                lines.append("")

            if funnel.stage_contract_to_python and funnel.stage_contract_to_python.leaks:
                lines.append("  💧 LEAKS AT CONTRACT → PYTHON (Required Only):")
                for leak in funnel.stage_contract_to_python.leaks[:3]:
                    lines.append(f"     - {leak['contract']}")
                    lines.append(f"       Producer: {leak.get('producer', 'unknown')}")
                    if leak.get('consumers'):
                        lines.append(f"       Consumers: {len(leak['consumers'])} wagon(s)")
                if len(funnel.stage_contract_to_python.leaks) > 3:
                    lines.append(f"     ... and {len(funnel.stage_contract_to_python.leaks) - 3} more")
                lines.append("")

        # Key insights
        lines.append("=" * 80)
        lines.append("💡 KEY INSIGHTS")
        lines.append("=" * 80)
        lines.append("")

        # Find worst leaks
        worst_python_leak = None
        for theme, funnel in result.by_theme.items():
            if funnel.python_missing_rate > 0:
                if not worst_python_leak or funnel.python_missing_rate > worst_python_leak[1]:
                    worst_python_leak = (theme, funnel.python_missing_rate, funnel.python_required - funnel.python_impl_count)

        if worst_python_leak:
            lines.append(f"⚠️  Biggest Python leak: '{worst_python_leak[0]}' ({worst_python_leak[2]} DTOs missing, {worst_python_leak[1]:.0f}% leak)")

        lines.append("")
        lines.append("💡 This funnel only shows DTOs required by actual producer/consumer wagons!")
        lines.append("")

        return "\n".join(lines)


class SmartImplementationReportFormatter:
    """
    Adapter: Format smart implementation reports with producer/consumer awareness.

    Shows only required DTOs based on actual producer/consumer tech stacks.
    """

    @staticmethod
    def format_report(requirements: List[ContractRequirements]) -> str:
        """Format smart implementation report."""
        lines = []

        lines.append("=" * 80)
        lines.append("SMART IMPLEMENTATION TRACEABILITY (Producer/Consumer Aware)")
        lines.append("=" * 80)
        lines.append("")

        # Calculate statistics
        total = len(requirements)
        fully_covered = sum(1 for r in requirements if r.coverage_percentage == 100)
        partially_covered = sum(1 for r in requirements if 0 < r.coverage_percentage < 100)
        not_covered = sum(1 for r in requirements if r.coverage_percentage == 0)

        requires_python = sum(1 for r in requirements if r.requires_python)
        requires_dart = sum(1 for r in requirements if r.requires_dart)
        requires_ts = sum(1 for r in requirements if r.requires_typescript)

        has_python = sum(1 for r in requirements if r.has_python and r.requires_python)
        has_dart = sum(1 for r in requirements if r.has_dart and r.requires_dart)
        has_ts = sum(1 for r in requirements if r.has_typescript and r.requires_typescript)

        # Summary
        lines.append("📊 SUMMARY")
        lines.append(f"   Total Contracts: {total}")
        lines.append(f"   Fully Covered (100%): {fully_covered}")
        lines.append(f"   Partially Covered: {partially_covered}")
        lines.append(f"   Not Covered (0%): {not_covered}")
        lines.append("")
        lines.append("   REQUIREMENTS (Based on Producer/Consumer Tech Stacks):")
        lines.append(f"   Python Required: {requires_python} contracts ({has_python} implemented, {requires_python - has_python} missing)")
        lines.append(f"   Dart Required: {requires_dart} contracts ({has_dart} implemented, {requires_dart - has_dart} missing)")
        lines.append(f"   TypeScript Required: {requires_ts} contracts ({has_ts} implemented, {requires_ts - has_ts} missing)")
        lines.append("")

        # Group by coverage
        incomplete = [r for r in requirements if r.coverage_percentage < 100]
        incomplete.sort(key=lambda r: r.coverage_percentage)

        if incomplete:
            lines.append("=" * 80)
            lines.append("⚠️  INCOMPLETE CONTRACTS (Missing Required DTOs)")
            lines.append("=" * 80)
            lines.append("")

            for req in incomplete[:20]:  # Show first 20
                coverage_emoji = "🔴" if req.coverage_percentage == 0 else "⚠️ "
                lines.append(f"{coverage_emoji} {req.contract_urn} ({req.coverage_percentage:.0f}% coverage)")
                lines.append(f"  Schema: {req.schema_path}")
                lines.append(f"  Producer: {req.producer or 'unknown'}")
                if req.consumers:
                    lines.append(f"  Consumers: {', '.join(req.consumers)}")
                lines.append("")

                # Python requirements
                if req.requires_python:
                    if req.has_python:
                        lines.append(f"  ✅ Python: Implemented")
                    else:
                        lines.append(f"  ❌ Python: MISSING")
                        if req.python_path_suggestion:
                            lines.append(f"     💡 Create: {req.python_path_suggestion}")

                # Dart requirements
                if req.requires_dart:
                    if req.has_dart:
                        lines.append(f"  ✅ Dart: Implemented")
                    else:
                        lines.append(f"  ❌ Dart: MISSING")
                        if req.dart_path_suggestion:
                            lines.append(f"     💡 Create: {req.dart_path_suggestion}")

                # TypeScript requirements
                if req.requires_typescript:
                    if req.has_typescript:
                        lines.append(f"  ✅ TypeScript: Implemented")
                    else:
                        lines.append(f"  ❌ TypeScript: MISSING")
                        if req.typescript_path_suggestion:
                            lines.append(f"     💡 Create: {req.typescript_path_suggestion}")

                lines.append("")

            if len(incomplete) > 20:
                lines.append(f"... and {len(incomplete) - 20} more incomplete contracts")
                lines.append("")

        # Fully covered contracts
        complete = [r for r in requirements if r.coverage_percentage == 100]
        if complete:
            lines.append("=" * 80)
            lines.append(f"✅ FULLY COVERED CONTRACTS ({len(complete)})")
            lines.append("=" * 80)
            lines.append("")

            for req in complete[:10]:  # Show first 10
                lines.append(f"✅ {req.contract_urn}")
                lines.append(f"  Producer: {req.producer or 'unknown'}")
                impl_langs = []
                if req.requires_python:
                    impl_langs.append("Python")
                if req.requires_dart:
                    impl_langs.append("Dart")
                if req.requires_typescript:
                    impl_langs.append("TypeScript")
                lines.append(f"  Implemented: {', '.join(impl_langs)}")
                lines.append("")

            if len(complete) > 10:
                lines.append(f"... and {len(complete) - 10} more fully covered contracts")
                lines.append("")

        # Key insights
        lines.append("=" * 80)
        lines.append("💡 KEY INSIGHTS")
        lines.append("=" * 80)
        lines.append("")

        python_missing_rate = ((requires_python - has_python) / requires_python * 100) if requires_python > 0 else 0
        dart_missing_rate = ((requires_dart - has_dart) / requires_dart * 100) if requires_dart > 0 else 0
        ts_missing_rate = ((requires_ts - has_ts) / requires_ts * 100) if requires_ts > 0 else 0

        lines.append(f"⚠️  Python DTOs: {python_missing_rate:.1f}% of required DTOs are missing")
        lines.append(f"⚠️  Dart Entities: {dart_missing_rate:.1f}% of required entities are missing")
        lines.append(f"⚠️  TypeScript Interfaces: {ts_missing_rate:.1f}% of required interfaces are missing")
        lines.append("")
        lines.append("💡 This report only shows DTOs required by actual producer/consumer wagons!")
        lines.append("")

        return "\n".join(lines)


class YAMLUpdater:
    """
    Adapter: Update YAML files pragmatically.

    Handles YAML file updates while preserving formatting.
    """

    def update_yaml_field(
        self,
        file_path: str,
        section: str,
        field_name: str,
        field_value: str,
        old_value: str = "null"
    ) -> bool:
        """
        Update a field in a YAML file.

        Args:
            file_path: Path to YAML file
            section: Section name (e.g., 'produce')
            field_name: Field to update (e.g., 'contract')
            field_value: New value
            old_value: Old value to replace (default: "null")

        Returns:
            True if successful, False otherwise
        """
        try:
            path = Path(file_path)

            if not path.exists():
                return False

            # Read file
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Replace using string manipulation (preserves formatting better than yaml.dump)
            # Pattern: "field_name: null" -> "field_name: value"
            pattern = f'{field_name}: {old_value}'
            replacement = f'{field_name}: {field_value}'

            updated_content = content.replace(pattern, replacement, 1)

            # Write back
            with open(path, 'w', encoding='utf-8') as f:
                f.write(updated_content)

            return True

        except Exception:
            return False


class TraceabilityFixer:
    """
    Adapter: Apply fixes to wagon manifests.

    Pragmatically updates manifest files with user approval.
    """

    def __init__(self):
        self.updater = YAMLUpdater()

    def apply_contract_fix(
        self,
        manifest_path: str,
        produce_name: str,
        contract_path: str
    ) -> bool:
        """
        Apply fix for missing contract reference.

        Updates wagon manifest YAML file to set contract field.
        """
        return self.updater.update_yaml_field(
            file_path=manifest_path,
            section='produce',
            field_name='contract',
            field_value=contract_path,
            old_value='null'
        )

    def apply_telemetry_fix(
        self,
        manifest_path: str,
        produce_name: str,
        telemetry_path: str
    ) -> bool:
        """
        Apply fix for missing telemetry reference.

        Updates wagon manifest YAML file to set telemetry field.
        """
        return self.updater.update_yaml_field(
            file_path=manifest_path,
            section='produce',
            field_name='telemetry',
            field_value=telemetry_path,
            old_value='null'
        )


# ============================================================================
# LAYER 4: COMMAND (CLI Orchestration)
# ============================================================================


def run_reconciliation(report_only: bool = True):
    """
    Run traceability reconciliation command.

    Args:
        report_only: If True, only show report. If False, prompt for fixes.
    """
    reconciler = TraceabilityReconciler()
    formatter = ReportFormatter()
    fixer = TraceabilityFixer()

    # Run reconciliation
    result = reconciler.reconcile_all()

    # Format and display report
    report = formatter.format_report(result)
    print(report)

    # If report_only mode, stop here
    if report_only or result.total_issues == 0:
        return

    # Interactive fix mode
    print("\n" + "=" * 70)
    print("🔧 FIX MODE")
    print("=" * 70)
    print()

    # Offer to fix contract references
    if result.missing_contract_refs:
        response = input(f"Fix {len(result.missing_contract_refs)} missing contract references? [y/N]: ")

        if response.lower() == 'y':
            for ref in result.missing_contract_refs:
                wagon = ref['wagon']
                manifest_path = result.by_wagon[wagon]['manifest_path']

                success = fixer.apply_contract_fix(
                    manifest_path=manifest_path,
                    produce_name=ref['produce_name'],
                    contract_path=ref['proposed_fix']
                )

                if success:
                    print(f"✅ Fixed {wagon} -> {ref['urn']}")
                else:
                    print(f"❌ Failed to fix {wagon} -> {ref['urn']}")

    # Offer to fix telemetry references
    if result.missing_telemetry_refs:
        response = input(f"Fix {len(result.missing_telemetry_refs)} missing telemetry references? [y/N]: ")

        if response.lower() == 'y':
            for ref in result.missing_telemetry_refs:
                wagon = ref['wagon']
                manifest_path = result.by_wagon[wagon]['manifest_path']

                success = fixer.apply_telemetry_fix(
                    manifest_path=manifest_path,
                    produce_name=ref['produce_name'],
                    telemetry_path=ref['proposed_fix']
                )

                if success:
                    print(f"✅ Fixed {wagon} -> {ref['urn']}")
                else:
                    print(f"❌ Failed to fix {wagon} -> {ref['urn']}")


# ============================================================================
# WMBT TEST TRACEABILITY VALIDATION
# ============================================================================


@dataclass
class WMBTTestFile:
    """
    A test file with WMBT code in its filename.

    Domain entity representing a test that traces to acceptance criteria.
    """
    file_path: str
    wmbt_code: str  # e.g., "C004", "E001"
    harness: str    # e.g., "UNIT", "HTTP", "E2E"
    sequence: str   # e.g., "001", "019"
    slug: Optional[str] = None
    wagon: Optional[str] = None


class WMBTTestFinder:
    """
    Use case: Find and parse test files using WMBT naming conventions.

    Test Naming Convention (from tester):
      Python: test_{wmbt_lower}_{harness_lower}_{nnn}[_{slug_snake}].py
      Dart: {WMBT}_{HARNESS}_{NNN}[_{slug_snake}]_test.dart
      TypeScript (backend): {wmbt}-{harness}-{nnn}[-{slug-kebab}].test.ts
      TypeScript (preact): {WMBT}_{HARNESS}_{NNN}[_{slug_snake}].test.ts[x]
      Go: {wmbt}_{harness}_{nnn}[_{slug_snake}]_test.go

    WMBT Format: {STEP}{NNN} where:
      - STEP: D|L|P|C|E|M|Y|R|K
      - NNN: 3-digit sequence (001-999)
    """

    # Test filename patterns by language
    PYTHON_TEST_PATTERN = re.compile(
        r'^test_([dlpcemyrk]\d{3})_([a-z0-9]+)_(\d{3})(?:_([a-z0-9_]+))?\.py$',
        re.IGNORECASE
    )

    DART_TEST_PATTERN = re.compile(
        r'^([DLPCEMYRK]\d{3})_([A-Z0-9]+)_(\d{3})(?:_([a-z0-9_]+))?_test\.dart$',
        re.IGNORECASE
    )

    TS_TEST_PATTERN = re.compile(
        r'^([dlpcemyrk]\d{3})-([a-z0-9]+)-(\d{3})(?:-([a-z0-9-]+))?\.test\.ts$',
        re.IGNORECASE
    )

    TS_PREACT_TEST_PATTERN = re.compile(
        r'^([DLPCEMYRK]\d{3})_([A-Z0-9]+)_(\d{3})(?:_([a-z0-9_]+))?\.test\.ts(?:x)?$',
        re.IGNORECASE
    )

    GO_TEST_PATTERN = re.compile(
        r'^([dlpcemyrk]\d{3})_([a-z0-9]+)_(\d{3})(?:_([a-z0-9_]+))?_test\.go$',
        re.IGNORECASE
    )

    # URN pattern for Dart tests (in comments)
    DART_URN_PATTERN = re.compile(
        r'//\s*urn:\s*acc:([a-z][a-z0-9-]*):([DLPCEMYRK]\d{3})-([A-Z0-9]+)-(\d{3})',
        re.IGNORECASE
    )

    def __init__(self, repo_root: Path = REPO_ROOT):
        self.repo_root = repo_root

    def find_all_test_files(self, languages: List[str] = None) -> List[WMBTTestFile]:
        """
        Find all test files following WMBT naming convention.

        Args:
            languages: List of languages to scan (default: ['python', 'dart', 'typescript', 'go'])

        Returns:
            List of WMBTTestFile objects
        """
        if languages is None:
            languages = ['python', 'dart', 'typescript', 'go']

        test_files = []

        for language in languages:
            if language == 'python':
                test_files.extend(self._find_python_tests())
            elif language == 'dart':
                test_files.extend(self._find_dart_tests())
            elif language in ['typescript', 'ts']:
                test_files.extend(self._find_typescript_tests())
            elif language == 'go':
                test_files.extend(self._find_go_tests())

        return test_files

    def _find_python_tests(self) -> List[WMBTTestFile]:
        """Find Python test files."""
        test_files = []
        test_dirs = [
            self.repo_root / 'python' / 'tests',
            self.repo_root / 'python',
            self.repo_root / 'tests',
        ]

        for test_dir in test_dirs:
            if not test_dir.exists():
                continue

            for test_file in test_dir.rglob('test_*.py'):
                parsed = self._parse_test_filename(test_file.name, 'python')
                if parsed:
                    wagon = self._infer_wagon_from_path(test_file)
                    test_files.append(WMBTTestFile(
                        file_path=str(test_file.relative_to(self.repo_root)),
                        wmbt_code=parsed['wmbt'],
                        harness=parsed['harness'],
                        sequence=parsed['nnn'],
                        slug=parsed['slug'],
                        wagon=wagon
                    ))

        return test_files

    def _find_dart_tests(self) -> List[WMBTTestFile]:
        """DEPRECATED: Dart/Flutter frontend removed in SESSION-18."""
        return []

    def _find_typescript_tests(self) -> List[WMBTTestFile]:
        """Find TypeScript test files."""
        test_files = []
        test_dirs = [
            self.repo_root / 'src',
            self.repo_root / 'test',
            self.repo_root / 'tests',
            self.repo_root / 'web' / 'tests',
        ]

        for test_dir in test_dirs:
            if not test_dir.exists():
                continue

            for pattern in ['*.test.ts', '*.test.tsx']:
                for test_file in test_dir.rglob(pattern):
                    parsed = self._parse_test_filename(test_file.name, 'typescript')
                    if parsed:
                        wagon = self._infer_wagon_from_path(test_file)
                        test_files.append(WMBTTestFile(
                            file_path=str(test_file.relative_to(self.repo_root)),
                            wmbt_code=parsed['wmbt'],
                            harness=parsed['harness'],
                            sequence=parsed['nnn'],
                            slug=parsed['slug'],
                            wagon=wagon
                        ))

        return test_files

    def _find_go_tests(self) -> List[WMBTTestFile]:
        """Find Go test files."""
        test_files = []
        test_dirs = [
            self.repo_root / 'pkg',
            self.repo_root / 'internal',
            self.repo_root / 'test',
        ]

        for test_dir in test_dirs:
            if not test_dir.exists():
                continue

            for test_file in test_dir.rglob('*_test.go'):
                parsed = self._parse_test_filename(test_file.name, 'go')
                if parsed:
                    wagon = self._infer_wagon_from_path(test_file)
                    test_files.append(WMBTTestFile(
                        file_path=str(test_file.relative_to(self.repo_root)),
                        wmbt_code=parsed['wmbt'],
                        harness=parsed['harness'],
                        sequence=parsed['nnn'],
                        slug=parsed['slug'],
                        wagon=wagon
                    ))

        return test_files

    def _parse_test_filename(self, filename: str, language: str) -> Optional[Dict[str, str]]:
        """
        Parse test filename to extract WMBT code, harness, and sequence.

        Args:
            filename: Test filename
            language: Language (python, dart, typescript, go)

        Returns:
            Dict with keys: wmbt, harness, nnn, slug (or None if invalid)
        """
        patterns = {
            'python': self.PYTHON_TEST_PATTERN,
            'dart': self.DART_TEST_PATTERN,
            'typescript': [self.TS_TEST_PATTERN, self.TS_PREACT_TEST_PATTERN],
            'ts': [self.TS_TEST_PATTERN, self.TS_PREACT_TEST_PATTERN],
            'go': self.GO_TEST_PATTERN,
        }

        pattern = patterns.get(language)
        if not pattern:
            return None

        if isinstance(pattern, list):
            match = None
            for candidate in pattern:
                match = candidate.match(filename)
                if match:
                    break
            if not match:
                return None
        else:
            match = pattern.match(filename)
            if not match:
                return None

        wmbt, harness, nnn, slug = match.groups()

        # Normalize to uppercase
        return {
            'wmbt': wmbt.upper(),
            'harness': harness.upper(),
            'nnn': nnn,
            'slug': slug
        }

    def _parse_dart_urn_comment(self, test_file: Path) -> Optional[Dict[str, str]]:
        """DEPRECATED: Dart/Flutter frontend removed in SESSION-18."""
        return None

    def _infer_wagon_from_path(self, test_file: Path) -> Optional[str]:
        """
        Infer wagon name from test file path.

        Common patterns:
          - python/tests/{wagon}/test_*.py
          - python/{wagon}/tests/test_*.py
        """
        parts = test_file.parts

        # Look for wagon directory names
        for i, part in enumerate(parts):
            if part in ['tests', 'test']:
                # Check previous part
                if i > 0:
                    candidate = parts[i - 1]
                    # Convert to wagon slug format
                    return candidate.replace('_', '-')
                # Check next part
                elif i < len(parts) - 1:
                    candidate = parts[i + 1]
                    if candidate not in ['test', 'tests'] and not candidate.endswith('.py'):
                        return candidate.replace('_', '-')

        return None


class WMBTAcceptanceParser:
    """
    Use case: Parse acceptance criteria files to extract WMBT codes.

    Finds WMBT codes declared in wagon acceptance YAML files.
    """

    # WMBT pattern in YAML acceptance files
    WMBT_PATTERN = re.compile(r'^([DLPCEMYRK])(\d{3})$')

    def __init__(self, plan_dir: Path = PLAN_DIR):
        self.plan_dir = plan_dir

    def extract_wmbt_codes_from_wagons_yaml(self) -> Dict[str, List[str]]:
        """
        Extract WMBT codes from the main _wagons.yaml file.

        Returns:
            Dict mapping wagon names to their WMBT codes
        """
        wagon_wmbts = {}
        wagons_yaml_path = self.plan_dir / '_wagons.yaml'

        if not wagons_yaml_path.exists():
            return wagon_wmbts

        try:
            with open(wagons_yaml_path, 'r') as f:
                data = yaml.safe_load(f)

            wagons = data.get('wagons', [])
            for wagon in wagons:
                wagon_name = wagon.get('wagon')
                if not wagon_name:
                    continue

                wmbts = []
                # Check for WMBT section
                wmbt_section = wagon.get('wmbt', {})

                # Some wagons list WMBTs directly as keys
                if isinstance(wmbt_section, dict):
                    for key in wmbt_section.keys():
                        # Skip metadata keys like 'total', 'coverage'
                        if self.WMBT_PATTERN.match(key):
                            wmbts.append(key)

                wagon_wmbts[wagon_name] = sorted(set(wmbts))

        except Exception:
            pass

        return wagon_wmbts

    def extract_wmbt_codes_from_wagon_dir(self, wagon_slug: str) -> List[str]:
        """
        Extract WMBT codes from a wagon's YAML files.

        Args:
            wagon_slug: Wagon slug (e.g., 'maintain-ux')

        Returns:
            List of WMBT codes found
        """
        wmbts = []
        wagon_dir = self.plan_dir / wagon_slug

        if not wagon_dir.exists() or not wagon_dir.is_dir():
            return wmbts

        # Find all YAML files except _*.yaml (manifests)
        yaml_files = [f for f in wagon_dir.glob('*.yaml') if not f.name.startswith('_')]

        for yaml_file in yaml_files:
            try:
                with open(yaml_file, 'r') as f:
                    content = yaml.safe_load(f)

                # Look for WMBT codes in acceptance criteria
                if isinstance(content, dict):
                    # Check for direct WMBT keys (e.g., C004, E001)
                    for key in content.keys():
                        if self.WMBT_PATTERN.match(key):
                            wmbts.append(key)

                    # Check nested 'acceptance' or 'wmbt' sections
                    for section_key in ['acceptance', 'wmbt', 'criteria', 'acceptance_criteria']:
                        section = content.get(section_key, {})
                        if isinstance(section, dict):
                            for key in section.keys():
                                if self.WMBT_PATTERN.match(key):
                                    wmbts.append(key)

            except Exception:
                pass

        return sorted(set(wmbts))


class WMBTTraceabilityValidator:
    """
    Use case: Validate WMBT test traceability.

    Ensures each test traces to an acceptance criterion via WMBT code.
    """

    def __init__(self):
        self.test_finder = WMBTTestFinder()
        self.acceptance_parser = WMBTAcceptanceParser()

    def validate_all(self) -> Dict[str, any]:
        """
        Run full WMBT traceability validation.

        Returns:
            Dict with validation results
        """
        # Find all test files
        test_files = self.test_finder.find_all_test_files()

        # Track by language
        by_language = defaultdict(int)
        for test in test_files:
            if test.file_path.endswith('.py'):
                by_language['python'] += 1
            elif test.file_path.endswith('.dart'):
                by_language['dart'] += 1
            elif test.file_path.endswith('.ts'):
                by_language['typescript'] += 1
            elif test.file_path.endswith('.go'):
                by_language['go'] += 1

        # Extract WMBT codes from wagons
        wagon_wmbts_manifest = self.acceptance_parser.extract_wmbt_codes_from_wagons_yaml()

        # Also check wagon directories
        wagon_wmbts = {}
        for wagon_name in wagon_wmbts_manifest.keys():
            wagon_slug = wagon_name.replace('_', '-')
            wmbts_from_dir = self.acceptance_parser.extract_wmbt_codes_from_wagon_dir(wagon_slug)

            # Combine both sources
            combined = set(wagon_wmbts_manifest.get(wagon_name, []))
            combined.update(wmbts_from_dir)
            wagon_wmbts[wagon_name] = sorted(combined)

        # Flatten all WMBT codes
        all_wmbts = set()
        for wmbts in wagon_wmbts.values():
            all_wmbts.update(wmbts)

        # Validate test files
        orphaned_tests = []
        valid_tests = []
        tests_by_wmbt = defaultdict(list)

        for test in test_files:
            wmbt = test.wmbt_code
            tests_by_wmbt[wmbt].append(test.file_path)

            if wmbt not in all_wmbts:
                orphaned_tests.append({
                    'file': test.file_path,
                    'wmbt': wmbt,
                    'harness': test.harness,
                    'wagon': test.wagon,
                    'reason': 'Test file has WMBT code not found in any acceptance criteria'
                })
            else:
                valid_tests.append(test.file_path)

        # Find missing tests (WMBT with no tests)
        missing_tests = []
        for wmbt in sorted(all_wmbts):
            if wmbt not in tests_by_wmbt:
                # Find which wagon owns this WMBT
                owner_wagons = [w for w, wmbts in wagon_wmbts.items() if wmbt in wmbts]
                missing_tests.append({
                    'wmbt': wmbt,
                    'wagons': owner_wagons,
                    'reason': 'Acceptance criterion exists but no test file found'
                })

        # Calculate coverage
        total_tests = len(test_files)
        valid_count = len(valid_tests)
        coverage = valid_count / total_tests if total_tests > 0 else 1.0

        return {
            'total_tests': total_tests,
            'valid_tests': valid_count,
            'orphaned_tests': orphaned_tests,
            'missing_tests': missing_tests,
            'coverage': coverage,
            'tests_by_wmbt': dict(tests_by_wmbt),
            'wagon_wmbts': wagon_wmbts,
            'by_language': dict(by_language)
        }


def format_wmbt_traceability_report(result: Dict[str, any]) -> str:
    """
    Format WMBT traceability validation report.

    Args:
        result: Validation result from WMBTTraceabilityValidator

    Returns:
        Formatted report string
    """
    lines = []

    lines.append("=" * 70)
    lines.append("WMBT TEST TRACEABILITY VALIDATION")
    lines.append("=" * 70)
    lines.append("")

    # Summary
    lines.append(f"📊 SUMMARY")
    lines.append(f"   Total Test Files: {result['total_tests']}")
    lines.append(f"   Valid Tests: {result['valid_tests']}")
    lines.append(f"   Orphaned Tests: {len(result['orphaned_tests'])}")
    lines.append(f"   Missing Tests: {len(result['missing_tests'])}")
    lines.append(f"   Coverage: {result['coverage']:.1%}")
    lines.append("")

    # Language breakdown
    if 'by_language' in result:
        lines.append(f"📚 BY LANGUAGE")
        for lang, count in sorted(result['by_language'].items()):
            lines.append(f"   {lang.capitalize()}: {count} test(s)")
        lines.append("")

    # Orphaned tests (tests without acceptance criteria)
    if result['orphaned_tests']:
        lines.append("=" * 70)
        lines.append("🔴 ORPHANED TESTS (No Acceptance Criteria)")
        lines.append("=" * 70)
        lines.append("")
        lines.append("These test files follow WMBT naming convention but their WMBT code")
        lines.append("is not found in any wagon's acceptance criteria.")
        lines.append("")

        for orphan in result['orphaned_tests']:
            lines.append(f"File: {orphan['file']}")
            lines.append(f"  WMBT: {orphan['wmbt']}")
            lines.append(f"  Harness: {orphan['harness']}")
            if orphan['wagon']:
                lines.append(f"  Inferred Wagon: {orphan['wagon']}")
            lines.append(f"  Issue: {orphan['reason']}")
            lines.append(f"  💡 FIX: Either add {orphan['wmbt']} to wagon acceptance criteria")
            lines.append(f"         or rename test file to use valid WMBT code")
            lines.append("")

    # Missing tests (acceptance criteria without tests)
    if result['missing_tests']:
        lines.append("=" * 70)
        lines.append("⚠️  MISSING TESTS (Acceptance Criteria Without Tests)")
        lines.append("=" * 70)
        lines.append("")
        lines.append("These WMBT codes are declared in acceptance criteria but no")
        lines.append("test files were found following the naming convention.")
        lines.append("")

        for missing in result['missing_tests']:
            lines.append(f"WMBT: {missing['wmbt']}")
            lines.append(f"  Wagons: {', '.join(missing['wagons'])}")
            lines.append(f"  Issue: {missing['reason']}")
            lines.append(f"  💡 FIX: Create test file following convention:")
            lines.append(f"         test_{missing['wmbt'].lower()}_{{harness}}_{{nnn}}.py")
            lines.append(f"         Example: test_{missing['wmbt'].lower()}_unit_001.py")
            lines.append("")

    # Test coverage by WMBT
    if result['tests_by_wmbt']:
        lines.append("=" * 70)
        lines.append("📋 TEST COVERAGE BY WMBT")
        lines.append("=" * 70)
        lines.append("")

        for wmbt in sorted(result['tests_by_wmbt'].keys()):
            tests = result['tests_by_wmbt'][wmbt]
            lines.append(f"{wmbt}: {len(tests)} test(s)")
            for test in tests:
                lines.append(f"  - {test}")
        lines.append("")

    return "\n".join(lines)


def run_wmbt_traceability_validation(verbose: bool = True):
    """
    Run WMBT test traceability validation command.

    Args:
        verbose: Show detailed report
    """
    validator = WMBTTraceabilityValidator()
    result = validator.validate_all()

    # Format and display report
    report = format_wmbt_traceability_report(result)
    print(report)

    # Return non-zero exit code if issues found
    return 1 if (result['orphaned_tests'] or result['missing_tests']) else 0


def run_implementation_reconciliation(verbose: bool = True):
    """
    Run contract implementation reconciliation command.

    Args:
        verbose: Show detailed report (default: True)
    """
    reconciler = ContractImplementationReconciler()
    formatter = ImplementationReportFormatter()

    # Run reconciliation
    result = reconciler.reconcile_all()

    # Format and display report
    report = formatter.format_report(result)
    print(report)

    # Return non-zero exit code if issues found
    return 1 if result.total_issues > 0 else 0


def run_funnel_analysis(verbose: bool = True):
    """
    Run traceability funnel analysis command.

    Args:
        verbose: Show detailed report (default: True)
    """
    analyzer = FunnelAnalyzer()
    formatter = FunnelReportFormatter()

    # Run analysis
    result = analyzer.analyze_funnel()

    # Format and display report
    report = formatter.format_report(result)
    print(report)

    # Return success (funnel is informational, not pass/fail)
    return 0


def run_smart_reconciliation(verbose: bool = True):
    """
    Run smart implementation reconciliation (producer/consumer aware).

    Args:
        verbose: Show detailed report (default: True)
    """
    reconciler = SmartImplementationReconciler()
    formatter = SmartImplementationReportFormatter()

    # Run smart reconciliation
    requirements = reconciler.reconcile_smart()

    # Format and display report
    report = formatter.format_report(requirements)
    print(report)

    # Return non-zero if missing requirements
    missing_count = sum(1 for r in requirements if r.coverage_percentage < 100)
    return 1 if missing_count > 0 else 0


def run_smart_funnel(verbose: bool = True):
    """
    Run smart funnel analysis (producer/consumer aware).

    Args:
        verbose: Show detailed report (default: True)
    """
    analyzer = SmartFunnelAnalyzer()
    formatter = SmartFunnelReportFormatter()

    # Run smart funnel analysis
    result = analyzer.analyze_smart_funnel()

    # Format and display report
    report = formatter.format_report(result)
    print(report)

    # Return success (funnel is informational)
    return 0


if __name__ == "__main__":
    import sys

    report_only = '--report' in sys.argv or '-r' in sys.argv
    wmbt_mode = '--wmbt' in sys.argv or '--test-traceability' in sys.argv
    impl_mode = '--impl' in sys.argv or '--implementations' in sys.argv
    funnel_mode = '--funnel' in sys.argv
    smart_mode = '--smart' in sys.argv
    smart_funnel_mode = '--smart-funnel' in sys.argv

    if smart_funnel_mode:
        # Run smart funnel analysis (producer/consumer aware, with visualization)
        exit_code = run_smart_funnel(verbose=True)
        sys.exit(exit_code)
    elif smart_mode:
        # Run smart implementation reconciliation (producer/consumer aware)
        exit_code = run_smart_reconciliation(verbose=True)
        sys.exit(exit_code)
    elif funnel_mode:
        # Run traceability funnel analysis
        exit_code = run_funnel_analysis(verbose=True)
        sys.exit(exit_code)
    elif impl_mode:
        # Run contract implementation reconciliation
        exit_code = run_implementation_reconciliation(verbose=True)
        sys.exit(exit_code)
    elif wmbt_mode:
        # Run WMBT test traceability validation
        exit_code = run_wmbt_traceability_validation(verbose=True)
        sys.exit(exit_code)
    else:
        # Run contract/telemetry reconciliation
        run_reconciliation(report_only=report_only)


# ============================================================================
# TRAIN URN VALIDATION
# ============================================================================

def validate_train_urns(verbose: bool = False) -> Dict[str, any]:
    """
    Validate train URNs in theme orchestrators.
    
    Checks:
    - Theme orchestrators in python/shared/ have train URNs
    - URN format: train:{theme}:{train_id}
    - Referenced train specs exist in plan/_trains/
    
    Returns:
        Dict with validation results
    """
    import re
    
    shared_dir = REPO_ROOT / "python" / "shared"
    trains_dir = REPO_ROOT / "plan" / "_trains"
    
    results = {
        'orchestrators_found': [],
        'missing_urns': [],
        'invalid_format': [],
        'missing_specs': [],
        'valid_urns': []
    }
    
    if not shared_dir.exists():
        return results
    
    # Find all train specs
    train_specs = set()
    if trains_dir.exists():
        for yaml_file in trains_dir.glob("*.yaml"):
            train_specs.add(yaml_file.stem)
    
    # Check each theme orchestrator
    for py_file in shared_dir.glob("*.py"):
        if py_file.name in ["__init__.py", "conftest.py"]:
            continue
            
        results['orchestrators_found'].append(py_file.name)
        
        # Extract train URNs from file
        urns = []
        with open(py_file, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if not stripped or not stripped.startswith('#'):
                    if urns:  # Stop after header section
                        break
                    continue
                
                match = re.match(r'#\s*urn:\s*train:([^:]+):(.+)', stripped)
                if match:
                    theme = match.group(1)
                    train_id = match.group(2).strip()
                    urns.append((theme, train_id, f"train:{theme}:{train_id}"))
        
        if not urns:
            results['missing_urns'].append({
                'file': py_file.name,
                'message': f"No train URNs found in {py_file.name}"
            })
            continue
        
        # Validate each URN
        theme_from_filename = py_file.stem
        for theme, train_id, full_urn in urns:
            # Check theme matches filename
            if theme != theme_from_filename:
                results['invalid_format'].append({
                    'file': py_file.name,
                    'urn': full_urn,
                    'issue': f"Theme '{theme}' doesn't match filename '{theme_from_filename}.py'"
                })
            
            # Check train_id format
            if not re.match(r'^\d{4}-[a-z][a-z0-9-]*$', train_id):
                results['invalid_format'].append({
                    'file': py_file.name,
                    'urn': full_urn,
                    'issue': f"Train ID '{train_id}' doesn't match pattern DDDD-kebab-case"
                })
            
            # Check train spec exists
            if train_id not in train_specs:
                results['missing_specs'].append({
                    'file': py_file.name,
                    'urn': full_urn,
                    'train_id': train_id,
                    'expected_path': f"plan/_trains/{train_id}.yaml"
                })
            else:
                results['valid_urns'].append({
                    'file': py_file.name,
                    'urn': full_urn,
                    'spec': f"plan/_trains/{train_id}.yaml"
                })
    
    # Print summary if verbose
    if verbose:
        print("\n" + "=" * 80)
        print("TRAIN URN VALIDATION")
        print("=" * 80)
        print(f"\nOrchestrators found: {len(results['orchestrators_found'])}")
        print(f"Valid URNs: {len(results['valid_urns'])}")
        print(f"Missing URNs: {len(results['missing_urns'])}")
        print(f"Invalid format: {len(results['invalid_format'])}")
        print(f"Missing specs: {len(results['missing_specs'])}")
        
        if results['valid_urns']:
            print("\n✅ Valid train URNs:")
            for item in results['valid_urns']:
                print(f"  {item['file']}: {item['urn']}")
        
        if results['missing_urns']:
            print("\n❌ Missing train URNs:")
            for item in results['missing_urns']:
                print(f"  {item['file']}: {item['message']}")
        
        if results['invalid_format']:
            print("\n❌ Invalid format:")
            for item in results['invalid_format']:
                print(f"  {item['file']}: {item['urn']}")
                print(f"    Issue: {item['issue']}")
        
        if results['missing_specs']:
            print("\n❌ Missing train specs:")
            for item in results['missing_specs']:
                print(f"  {item['file']}: {item['urn']}")
                print(f"    Expected: {item['expected_path']}")
    
    return results
