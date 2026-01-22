"""
Consumer Validation System - Validate and sync consumer declarations.

Architecture: 4-Layer Clean Architecture (single file)
- Domain: Pure business logic (mismatch detection, validation)
- Integration: File I/O adapters (YAML, JSON scanning)
- Application: Use cases (detect mismatches, apply updates)
- Presentation: CLI facade (ConsumerValidator)

Validates consumer declarations between:
- Wagon manifests (plan/*/_*.yaml)
- Feature manifests (plan/*/*/*.yaml)
- Contract schemas (contracts/**/*.schema.json)

This command helps maintain coherence between consumer declarations
in manifests and contract metadata.
"""
import yaml
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass


# ============================================================================
# DOMAIN LAYER - Pure Business Logic
# ============================================================================
# No I/O, pure functions and entities.
# Handles mismatch detection and validation logic.
# ============================================================================

@dataclass
class ConsumerMismatch:
    """Represents a consumer declaration mismatch."""
    type: str  # "manifest_to_contract" or "contract_to_manifest"
    manifest_file: Optional[str] = None
    contract_file: Optional[str] = None
    contract_ref: Optional[str] = None  # e.g., "contract:match:dilemma.current"
    consumer_ref: Optional[str] = None  # e.g., "wagon:test-wagon"


class ConsumerMismatchDetector:
    """Domain logic for detecting consumer mismatches."""

    @staticmethod
    def detect_manifest_to_contract_mismatches(
        manifest_consumers: Dict[str, List[str]],
        contract_consumers: Dict[str, List[str]],
        contract_id_map: Dict[str, str]
    ) -> List[ConsumerMismatch]:
        """
        Detect manifests declaring contracts that don't list them as consumers.

        Args:
            manifest_consumers: {manifest_path: [contract_refs]}
            contract_consumers: {contract_path: [consumer_refs]}
            contract_id_map: {contract_ref: contract_path} mapping

        Returns:
            List of mismatches where manifest declares contract but contract doesn't list it
        """
        mismatches = []

        for manifest_path, declared_contracts in manifest_consumers.items():
            for contract_ref in declared_contracts:
                # Extract wagon name from manifest path
                # e.g., plan/test_wagon/features/choose_option.yaml -> wagon:test-wagon
                parts = Path(manifest_path).parts
                if len(parts) >= 2 and parts[0] == "plan":
                    wagon_name = parts[1].replace("_", "-")
                    consumer_ref = f"wagon:{wagon_name}"

                    # Find the contract file using $id mapping
                    contract_file = ConsumerMismatchDetector._find_contract_file(
                        contract_ref, contract_id_map
                    )

                    if contract_file:
                        consumers = contract_consumers.get(contract_file, [])
                        if consumer_ref not in consumers:
                            mismatches.append(ConsumerMismatch(
                                type="manifest_to_contract",
                                manifest_file=manifest_path,
                                contract_file=contract_file,
                                contract_ref=contract_ref,
                                consumer_ref=consumer_ref
                            ))

        return mismatches

    @staticmethod
    def detect_contract_to_manifest_mismatches(
        manifest_consumers: Dict[str, List[str]],
        contract_consumers: Dict[str, List[str]]
    ) -> List[ConsumerMismatch]:
        """
        Detect contracts listing consumers not declared in any manifest.

        Args:
            manifest_consumers: {manifest_path: [contract_refs]}
            contract_consumers: {contract_path: [consumer_refs]}

        Returns:
            List of mismatches where contract lists consumer not in any manifest
        """
        mismatches = []

        # Build set of all declared consumers from manifests
        declared_consumers = set()
        for manifest_path in manifest_consumers.keys():
            parts = Path(manifest_path).parts
            if len(parts) >= 2 and parts[0] == "plan":
                wagon_name = parts[1].replace("_", "-")
                declared_consumers.add(f"wagon:{wagon_name}")

        # Check each contract's consumers
        for contract_path, consumers in contract_consumers.items():
            for consumer_ref in consumers:
                if consumer_ref.startswith("wagon:") and consumer_ref not in declared_consumers:
                    mismatches.append(ConsumerMismatch(
                        type="contract_to_manifest",
                        contract_file=contract_path,
                        consumer_ref=consumer_ref
                    ))

        return mismatches

    @staticmethod
    def _find_contract_file(contract_ref: str, contract_id_map: Dict[str, str]) -> Optional[str]:
        """
        Find contract file path from contract reference using $id mapping.

        Args:
            contract_ref: Contract reference like "contract:match:dilemma.current"
            contract_id_map: Mapping of contract refs to file paths

        Returns:
            File path if found, None otherwise
        """
        return contract_id_map.get(contract_ref)


# ============================================================================
# INTEGRATION LAYER - File I/O Adapters
# ============================================================================
# Handles reading/writing YAML and JSON files.
# Scanning filesystem for manifests and contracts.
# ============================================================================

class ManifestScanner:
    """Scans and parses wagon and feature manifests."""

    @staticmethod
    def scan_manifests(plan_dir: Path) -> Dict[str, List[str]]:
        """
        Scan all wagon and feature manifests for consumer declarations.

        Returns:
            Dict mapping manifest paths to list of contract references
        """
        manifest_consumers = {}

        # Scan wagon manifests (plan/*/_*.yaml)
        for wagon_manifest in plan_dir.glob("*/_*.yaml"):
            consumers = ManifestScanner._extract_consumers(wagon_manifest)
            if consumers:
                rel_path = str(wagon_manifest.relative_to(plan_dir.parent))
                manifest_consumers[rel_path] = consumers

        # Scan feature manifests (plan/*/*/*.yaml)
        for feature_manifest in plan_dir.glob("*/*/*.yaml"):
            # Skip wagon manifests (those starting with _)
            if not feature_manifest.name.startswith("_"):
                consumers = ManifestScanner._extract_consumers(feature_manifest)
                if consumers:
                    rel_path = str(feature_manifest.relative_to(plan_dir.parent))
                    manifest_consumers[rel_path] = consumers

        return manifest_consumers

    @staticmethod
    def _extract_consumers(manifest_path: Path) -> List[str]:
        """
        Extract consumer contract references from manifest.

        Recognizes two patterns:
        1. Pattern A (standalone): - name: contract:domain:resource
        2. Pattern B (annotation): - name: artifact
                                      contract: contract:domain:resource
        """
        try:
            with open(manifest_path) as f:
                data = yaml.safe_load(f)

            if not data:
                return []

            consumers = []
            consume_list = data.get("consume", [])

            for item in consume_list:
                if isinstance(item, dict):
                    # Pattern A: name field starts with "contract:"
                    if "name" in item:
                        consumer_name = item["name"]
                        if consumer_name.startswith("contract:"):
                            consumers.append(consumer_name)

                    # Pattern B: contract field annotation
                    if "contract" in item:
                        contract_ref = item["contract"]
                        if contract_ref and contract_ref.startswith("contract:"):
                            consumers.append(contract_ref)

            return consumers
        except Exception:
            return []


class ContractScanner:
    """Scans and parses contract schemas."""

    @staticmethod
    def scan_contracts(contracts_dir: Path) -> Dict[str, List[str]]:
        """
        Scan all contract schemas for consumer declarations.

        Returns:
            Dict mapping contract paths to list of consumer references
        """
        contract_consumers = {}

        for contract_file in contracts_dir.glob("**/*.schema.json"):
            consumers = ContractScanner._extract_consumers(contract_file)
            rel_path = str(contract_file.relative_to(contracts_dir.parent))
            contract_consumers[rel_path] = consumers

        return contract_consumers

    @staticmethod
    def scan_contract_ids(contracts_dir: Path) -> Dict[str, str]:
        """
        Scan all contract schemas and map $id to file path.

        Returns:
            Dict mapping contract $id to file path
        """
        contract_id_map = {}

        for contract_file in contracts_dir.glob("**/*.schema.json"):
            contract_id = ContractScanner._extract_contract_id(contract_file)
            if contract_id:
                rel_path = str(contract_file.relative_to(contracts_dir.parent))
                contract_id_map[f"contract:{contract_id}"] = rel_path

        return contract_id_map

    @staticmethod
    def _extract_consumers(contract_path: Path) -> List[str]:
        """Extract consumer references from contract metadata."""
        try:
            with open(contract_path) as f:
                data = json.load(f)

            metadata = data.get("x-artifact-metadata", {})
            return metadata.get("consumers", [])
        except Exception:
            return []

    @staticmethod
    def _extract_contract_id(contract_path: Path) -> Optional[str]:
        """Extract $id from contract schema."""
        try:
            with open(contract_path) as f:
                data = json.load(f)

            return data.get("$id")
        except Exception:
            return None


class FileUpdater:
    """Updates manifest and contract files."""

    @staticmethod
    def update_manifest(manifest_path: Path, contract_ref: str) -> bool:
        """Add contract reference to manifest consume list."""
        try:
            with open(manifest_path) as f:
                data = yaml.safe_load(f)

            if not data:
                data = {}

            if "consume" not in data:
                data["consume"] = []

            # Check for duplicates
            existing = {item.get("name") for item in data["consume"] if isinstance(item, dict)}
            if contract_ref not in existing:
                data["consume"].append({"name": contract_ref})

            # Write back preserving format
            with open(manifest_path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

            return True
        except Exception as e:
            print(f"Error updating manifest {manifest_path}: {e}")
            return False

    @staticmethod
    def update_contract(contract_path: Path, consumer_ref: str) -> bool:
        """Add consumer reference to contract metadata."""
        try:
            with open(contract_path) as f:
                data = json.load(f)

            metadata = data.get("x-artifact-metadata", {})
            if "consumers" not in metadata:
                metadata["consumers"] = []

            # Check for duplicates
            if consumer_ref not in metadata["consumers"]:
                metadata["consumers"].append(consumer_ref)

            data["x-artifact-metadata"] = metadata

            # Write back preserving format
            with open(contract_path, 'w') as f:
                json.dump(data, f, indent=2)

            return True
        except Exception as e:
            print(f"Error updating contract {contract_path}: {e}")
            return False

    @staticmethod
    def remove_contract_consumer(contract_path: Path, consumer_ref: str) -> bool:
        """Remove consumer reference from contract metadata."""
        try:
            with open(contract_path) as f:
                data = json.load(f)

            metadata = data.get("x-artifact-metadata", {})
            if "consumers" in metadata and consumer_ref in metadata["consumers"]:
                metadata["consumers"].remove(consumer_ref)

            data["x-artifact-metadata"] = metadata

            # Write back preserving format
            with open(contract_path, 'w') as f:
                json.dump(data, f, indent=2)

            return True
        except Exception as e:
            print(f"Error removing consumer from contract {contract_path}: {e}")
            return False


# ============================================================================
# APPLICATION LAYER - Use Cases & Orchestration
# ============================================================================
# Coordinates domain and integration layers.
# Contains validation and sync workflow orchestration.
# ============================================================================

class ConsumerValidationUseCase:
    """Use case for validating consumer declarations."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.plan_dir = repo_root / "plan"
        self.contracts_dir = repo_root / "contracts"

    def detect_mismatches(self) -> Dict[str, Any]:
        """
        Detect all consumer mismatches between manifests and contracts.

        Returns:
            Report with manifest_to_contract and contract_to_manifest mismatches
        """
        # Scan files
        manifest_consumers = ManifestScanner.scan_manifests(self.plan_dir)
        contract_consumers = ContractScanner.scan_contracts(self.contracts_dir)
        contract_id_map = ContractScanner.scan_contract_ids(self.contracts_dir)

        # Detect mismatches
        manifest_to_contract = ConsumerMismatchDetector.detect_manifest_to_contract_mismatches(
            manifest_consumers, contract_consumers, contract_id_map
        )
        contract_to_manifest = ConsumerMismatchDetector.detect_contract_to_manifest_mismatches(
            manifest_consumers, contract_consumers
        )

        # Convert to dict format
        return {
            "manifest_to_contract": [
                {
                    "manifest": m.manifest_file,
                    "contract": m.contract_ref,
                    "contract_file": m.contract_file,
                    "consumer": m.consumer_ref
                }
                for m in manifest_to_contract
            ],
            "contract_to_manifest": [
                {
                    "contract_file": m.contract_file,
                    "consumer": m.consumer_ref
                }
                for m in contract_to_manifest
            ]
        }


class ConsumerSyncUseCase:
    """Use case for syncing consumer declarations."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def apply_updates(self, updates: List[Dict], direction: str) -> Dict[str, Any]:
        """
        Apply consumer synchronization updates.

        Args:
            updates: List of update operations
            direction: "manifests", "contracts", or "mutual"

        Returns:
            Summary report of applied changes
        """
        applied = 0
        errors = []

        for update in updates:
            update_type = update.get("type", "manifest_to_contract")

            # Direction 1: manifest_to_contract updates
            if direction in ["manifests", "mutual"] and update_type == "manifest_to_contract":
                # Update manifest
                manifest_path = self.repo_root / update["manifest_file"]
                contract_ref = update["contract_ref"]
                if FileUpdater.update_manifest(manifest_path, contract_ref):
                    applied += 1
                else:
                    errors.append(f"Failed to update {update['manifest_file']}")

            if direction in ["contracts", "mutual"] and update_type == "manifest_to_contract":
                # Update contract
                contract_path = self.repo_root / update["contract_file"]
                consumer_ref = update["consumer_ref"]
                if FileUpdater.update_contract(contract_path, consumer_ref):
                    applied += 1
                else:
                    errors.append(f"Failed to update {update['contract_file']}")

            # Direction 2: contract_to_manifest updates
            if direction in ["manifests", "mutual"] and update_type == "contract_to_manifest":
                # Add consume declaration to manifest
                manifest_path = self.repo_root / update["manifest_file"]
                contract_ref = update["contract_ref"]
                if FileUpdater.update_manifest(manifest_path, contract_ref):
                    applied += 1
                else:
                    errors.append(f"Failed to update {update['manifest_file']}")

            if direction in ["contracts", "mutual"] and update_type == "contract_to_manifest":
                # Remove invalid consumer from contract
                contract_path = self.repo_root / update["contract_file"]
                consumer_ref = update["consumer_ref"]
                if FileUpdater.remove_contract_consumer(contract_path, consumer_ref):
                    applied += 1
                else:
                    errors.append(f"Failed to remove consumer from {update['contract_file']}")

        return {
            "applied": applied,
            "errors": errors
        }


# ============================================================================
# PRESENTATION LAYER - CLI Facade
# ============================================================================
# Public API for consumer validation and syncing.
# Delegates to application layer use cases.
# ============================================================================

class ConsumerValidator:
    """
    Validates and syncs consumer declarations between manifests and contracts.

    Usage:
        validator = ConsumerValidator(repo_root)
        report = validator.detect_mismatches()
        summary = validator.apply_updates(updates, direction="mutual")
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.validation_use_case = ConsumerValidationUseCase(self.repo_root)
        self.sync_use_case = ConsumerSyncUseCase(self.repo_root)

    def detect_mismatches(self) -> Dict[str, Any]:
        """
        Detect consumer mismatches between manifests and contracts.

        Returns:
            Report dict with:
            - manifest_to_contract: List of manifests declaring contracts not listing them
            - contract_to_manifest: List of contracts listing undeclared consumers
        """
        return self.validation_use_case.detect_mismatches()

    def apply_updates(self, updates: List[Dict], direction: str = "mutual") -> Dict[str, Any]:
        """
        Apply consumer synchronization updates.

        Args:
            updates: List of update operations from detect_mismatches
            direction: "manifests", "contracts", or "mutual" (default)

        Returns:
            Summary dict with applied count and errors
        """
        return self.sync_use_case.apply_updates(updates, direction)


# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == "__main__":
    import sys

    # Check for --fix flag
    fix_mode = "--fix" in sys.argv

    # Run consumer validation
    repo_root = Path.cwd()
    validator = ConsumerValidator(repo_root)
    report = validator.detect_mismatches()

    # Display results
    print('=' * 80)
    print('CONSUMER VALIDATION REPORT')
    print('=' * 80)

    manifest_to_contract = report['manifest_to_contract']
    contract_to_manifest = report['contract_to_manifest']

    print(f'\n📋 DIRECTION 1: Manifest→Contract Mismatches')
    print(f'   Manifests declaring contracts that don\'t list them as consumers')
    print(f'   Found: {len(manifest_to_contract)} mismatches\n')

    if manifest_to_contract:
        for i, mismatch in enumerate(manifest_to_contract, 1):
            print(f'   {i}. Manifest: {mismatch["manifest"]}')
            print(f'      Declares: {mismatch["contract"]}')
            print(f'      Contract: {mismatch["contract_file"]}')
            print(f'      Missing consumer: {mismatch["consumer"]}')
            print()
    else:
        print('   ✓ No mismatches found\n')

    print(f'📋 DIRECTION 2: Contract→Manifest Mismatches')
    print(f'   Contracts listing consumers not declared in any manifest')
    print(f'   Found: {len(contract_to_manifest)} mismatches\n')

    if contract_to_manifest:
        for i, mismatch in enumerate(contract_to_manifest, 1):
            print(f'   {i}. Contract: {mismatch["contract_file"]}')
            print(f'      Lists consumer: {mismatch["consumer"]}')
            print(f'      Not found in any manifest')
            print()
    else:
        print('   ✓ No mismatches found\n')

    # Exit if no mismatches found
    if len(manifest_to_contract) == 0 and len(contract_to_manifest) == 0:
        print('✓ All consumer declarations are in sync!')
        sys.exit(0)

    # Fix mode - ask for direction and approval
    if fix_mode:
        print('=' * 80)
        print('FIX MODE - SELECT DIRECTION')
        print('=' * 80)
        print('1. Update manifests only - Add contract refs to wagon/feature consume lists')
        print('2. Update contracts only - Add wagon refs to contract x-artifact-metadata.consumers')
        print('3. Mutual sync (both) - Sync both directions [RECOMMENDED]')
        print('=' * 80)

        direction_choice = input('\nSelect fix direction (1/2/3) or cancel (c): ').strip()

        if direction_choice == 'c':
            print('❌ Cancelled by user')
            sys.exit(0)

        direction_map = {
            '1': 'manifests',
            '2': 'contracts',
            '3': 'mutual'
        }

        direction = direction_map.get(direction_choice)
        if not direction:
            print('❌ Invalid choice')
            sys.exit(1)

        # Show preview of changes
        print('\n' + '=' * 80)
        print('PREVIEW OF CHANGES')
        print('=' * 80)

        changes_count = 0
        all_updates = []

        # Direction 1: Manifest→Contract mismatches
        if direction in ['manifests', 'mutual'] and manifest_to_contract:
            print('\n📝 MANIFESTS TO UPDATE (Direction 1):')
            for mismatch in manifest_to_contract:
                print(f'\n   File: {mismatch["manifest"]}')
                print(f'   Will add: consume:')
                print(f'             - name: {mismatch["contract"]}')
                changes_count += 1
                all_updates.append(mismatch)

        if direction in ['contracts', 'mutual'] and manifest_to_contract:
            print('\n📝 CONTRACTS TO UPDATE (Direction 1):')
            for mismatch in manifest_to_contract:
                print(f'\n   File: {mismatch["contract_file"]}')
                print(f'   Will add to x-artifact-metadata.consumers:')
                print(f'             - {mismatch["consumer"]}')
                changes_count += 1

        # Direction 2: Contract→Manifest mismatches
        if direction in ['manifests', 'mutual'] and contract_to_manifest:
            print('\n📝 MANIFESTS TO UPDATE (Direction 2):')
            print('   Adding consume declarations to wagon manifests\n')
            for mismatch in contract_to_manifest:
                # Extract wagon name and construct manifest path
                consumer_ref = mismatch["consumer"]
                if consumer_ref.startswith("wagon:"):
                    wagon_name = consumer_ref.replace("wagon:", "").replace("-", "_")
                    manifest_path = f"plan/{wagon_name}/_{wagon_name}.yaml"

                    # Extract contract ref from contract file
                    contract_file = mismatch["contract_file"]
                    # e.g., contracts/commons/identifiers/username.schema.json -> contract:system:identifiers
                    parts = Path(contract_file).parts
                    if len(parts) >= 4 and parts[0] == "contracts":
                        domain = parts[1]
                        resource = parts[2]
                        contract_ref = f"contract:{domain}:{resource}"

                        print(f'   File: {manifest_path}')
                        print(f'   Will add: consume:')
                        print(f'             - name: {contract_ref}')
                        print()

                        changes_count += 1
                        all_updates.append({
                            "type": "contract_to_manifest",
                            "manifest_file": manifest_path,
                            "contract_file": contract_file,
                            "contract_ref": contract_ref,
                            "consumer_ref": consumer_ref
                        })

        if direction in ['contracts', 'mutual'] and contract_to_manifest:
            print('\n📝 CONTRACTS TO UPDATE (Direction 2):')
            print('   Removing invalid consumer references\n')
            for mismatch in contract_to_manifest:
                print(f'   File: {mismatch["contract_file"]}')
                print(f'   Will remove from x-artifact-metadata.consumers:')
                print(f'             - {mismatch["consumer"]}')
                print()
                changes_count += 1

        print(f'\n   Total changes: {changes_count}')
        print('=' * 80)

        # Ask for final approval
        approval = input('\nApply these changes? (yes/no): ').strip().lower()

        if approval not in ['yes', 'y']:
            print('❌ Changes not applied')
            sys.exit(0)

        # Apply updates
        print('\n🔧 Applying updates...\n')
        summary = validator.apply_updates(all_updates, direction=direction)

        print('=' * 80)
        print('SUMMARY')
        print('=' * 80)
        print(f'✓ Applied: {summary["applied"]} updates')

        if summary.get("errors"):
            print(f'\n❌ Errors: {len(summary["errors"])}')
            for error in summary["errors"]:
                print(f'   - {error}')
        else:
            print('✓ No errors')

        print('=' * 80)
        print('\n✓ Consumer synchronization complete!')

    else:
        # Not in fix mode - show instructions
        print('=' * 80)
        print('NEXT STEPS')
        print('=' * 80)
        print('Run with --fix to apply updates:')
        print('  python3 atdd/coach/commands/consumers.py --fix')
        print('=' * 80)
        sys.exit(1)
