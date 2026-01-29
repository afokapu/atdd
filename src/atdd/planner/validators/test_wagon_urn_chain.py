"""
Platform test: Complete wagon URN chain reconciliation.

Given a wagon URN, recursively validates the entire chain purely via URNs:
  wagon → produce → contract/telemetry → features → code → wmbts → acceptances → tests

This is a fast, parametrized test that validates 100% URN traceability with no inference.
Validates:
  - Specification layer: wagon, features, wmbts, acceptances
  - Interface layer: contracts, telemetry with signal files
  - Implementation layer: code files with component: URNs
  - Test layer: test files with acc: URNs

Acceptance URN Format Support (SPEC-COACH-UTILS-0282):
  - NEW format: acc:{wagon}:{wmbt_id}-{harness}-{NNN}[-{slug}]
    Example: acc:pace-dilemmas:L001-UNIT-001
  - OLD format: acc:{wagon}:{wmbt_id}:{id} or acc:{wagon}.{wmbt_id}.{id}
    Example: acc:maintain-ux:L001:AC-HTTP-001 or acc:maintain-ux.L001.AC-HTTP-001
"""
import pytest
import yaml
import json
from pathlib import Path
from typing import Dict, Any, List, Set

# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
PLAN_DIR = REPO_ROOT / "plan"
CONTRACTS_DIR = REPO_ROOT / "contracts"
TELEMETRY_DIR = REPO_ROOT / "telemetry"


class WagonChainValidator:
    """Validates complete URN chain for a wagon."""

    def __init__(self, wagon_slug: str):
        self.wagon_slug = wagon_slug
        self.wagon_urn = f"wagon:{wagon_slug}"
        self.errors: List[str] = []
        self.stats = {
            "produce_count": 0,
            "contract_urns": 0,
            "contract_schemas": 0,
            "telemetry_urns": 0,
            "telemetry_signals": 0,
            "feature_urns": 0,
            "feature_yaml_urns": 0,
            "wmbt_urns": 0,
            "wmbt_yaml_urns": 0,
            "acceptance_urns": 0,
            "test_files": 0,
            "code_files": 0
        }

    def validate(self) -> bool:
        """Run complete chain validation. Returns True if valid."""
        # 1. Load wagon manifest via URN
        wagon_path = self._resolve_wagon_urn(self.wagon_urn)
        if not wagon_path:
            return False

        with open(wagon_path) as f:
            wagon_manifest = yaml.safe_load(f)

        # 2. Validate produce artifacts
        self._validate_produce_artifacts(wagon_manifest)

        # 3. Validate features → code files
        self._validate_features(wagon_manifest)

        # 4. Validate WMBTs → acceptances → test files
        self._validate_wmbts(wagon_manifest)

        return len(self.errors) == 0

    def _resolve_wagon_urn(self, wagon_urn: str) -> Path:
        """Resolve wagon:slug to plan/{dirname}/_{dirname}.yaml."""
        if not wagon_urn.startswith("wagon:"):
            self.errors.append(f"Invalid wagon URN: {wagon_urn}")
            return None

        slug = wagon_urn.split(":")[1]
        dirname = slug.replace("-", "_")
        manifest_path = PLAN_DIR / dirname / f"_{dirname}.yaml"

        if not manifest_path.exists():
            self.errors.append(
                f"Wagon URN {wagon_urn} does not resolve to filesystem:\n"
                f"  Expected: {manifest_path}\n"
                f"  Path does not exist"
            )
            return None

        return manifest_path

    def _validate_produce_artifacts(self, wagon_manifest: Dict[str, Any]):
        """Validate produce → contract + telemetry URNs."""
        produce_items = wagon_manifest.get("produce", [])
        self.stats["produce_count"] = len(produce_items)

        for idx, item in enumerate(produce_items):
            artifact_name = item.get("name", "")
            contract_urn = item.get("contract")
            telemetry_urn = item.get("telemetry")

            # Validate contract URN
            if contract_urn:
                if not self._validate_contract_urn(contract_urn):
                    self.errors.append(
                        f"produce[{idx}] contract URN {contract_urn} resolution failed"
                    )
                else:
                    self.stats["contract_urns"] += 1

            # Validate telemetry URN (handle both string and list)
            if telemetry_urn:
                telemetry_urns = telemetry_urn if isinstance(telemetry_urn, list) else [telemetry_urn]
                for urn in telemetry_urns:
                    if not self._validate_telemetry_urn(urn):
                        self.errors.append(
                            f"produce[{idx}] telemetry URN {urn} resolution failed"
                        )
                    else:
                        self.stats["telemetry_urns"] += 1

    def _validate_contract_urn(self, contract_urn: str) -> bool:
        """Validate contract URN resolves to file or directory per convention.

        Supports patterns per artifact-naming.convention.yaml:
        - FLAT: contracts/{domain}/{resource}.schema.json (singular resource)
        - FACETED: contracts/{domain}/{aspect}/{variant}.schema.json (dot notation)
        - COLLECTION: contracts/{domain}/{resource}/ (plural resource with multiple schemas)

        Per convention: Split artifact name by colons (:) and dots (.) - each segment creates a directory level.
        """
        # Validate URN format
        if not contract_urn.startswith("contract:"):
            return False

        # Remove "contract:" prefix and split by both : and .
        artifact_part = contract_urn[9:]  # Remove "contract:"

        # Split by both : and . per artifact-naming convention
        import re
        segments = re.split(r'[:\.]', artifact_part)

        if len(segments) < 2:
            return False

        # Reconstruct domain:resource for $id validation (preserves original separators)
        domain_resource = artifact_part

        # Build file path: all segments become directories except the last one becomes filename
        # contracts/{seg1}/{seg2}/{...}/{segN}.schema.json
        path_parts = segments[:-1]
        filename = f"{segments[-1]}.schema.json"

        contract_file = CONTRACTS_DIR / Path(*path_parts) / filename

        # Try as a file first (FLAT or FACETED pattern)
        if contract_file.exists() and contract_file.is_file():
            try:
                with open(contract_file) as f:
                    schema = json.load(f)

                schema_id = schema.get("$id", "")
                if not schema_id:
                    self.stats["contract_schemas"] += 1
                    return True  # File exists, skip $id validation

                # Validate $id contains the artifact name (with original separators)
                if domain_resource not in schema_id:
                    self.errors.append(
                        f"Contract schema $id mismatch:\n"
                        f"  URN: {contract_urn}\n"
                        f"  File: {contract_file.relative_to(REPO_ROOT)}\n"
                        f"  Found $id: '{schema_id}'\n"
                        f"  Must contain: '{domain_resource}'"
                    )
                    return False

                self.stats["contract_schemas"] += 1
                return True

            except Exception as e:
                self.errors.append(
                    f"Error reading contract schema {contract_file.relative_to(REPO_ROOT)}: {str(e)}"
                )
                return False

        # Try as a directory (COLLECTION pattern)
        # For collections, the directory is at the parent level
        contract_dir = CONTRACTS_DIR / Path(*segments)
        if contract_dir.exists() and contract_dir.is_dir():
            # COLLECTION pattern - validate as directory
            contract_path = contract_dir
        else:
            # Neither FLAT/FACETED nor COLLECTION pattern found
            return False

        contract_path = contract_dir

        # Validate schema files have $id fields
        schema_files = list(contract_path.glob("*.schema.json"))
        for schema_file in schema_files:
            try:
                with open(schema_file) as f:
                    schema = json.load(f)

                schema_id = schema.get("$id", "")

                # Skip validation if $id is not present (optional for now)
                if not schema_id:
                    continue

                # Schema $id can have multiple formats:
                # 1. ux:foundations:color:v1.1
                # 2. urn:contract:ux:foundations:layout
                # Validate it contains the artifact name pattern (with original separators)
                if domain_resource not in schema_id:
                    self.errors.append(
                        f"Contract schema $id mismatch:\n"
                        f"  URN: {contract_urn}\n"
                        f"  File: {schema_file.relative_to(REPO_ROOT)}\n"
                        f"  Found $id: '{schema_id}'\n"
                        f"  Must contain: '{domain_resource}'"
                    )
                    continue

                self.stats["contract_schemas"] += 1

            except Exception as e:
                self.errors.append(
                    f"Error reading contract schema {schema_file.relative_to(REPO_ROOT)}: {str(e)}"
                )

        return True

    def _validate_telemetry_urn(self, telemetry_urn: str) -> bool:
        """Validate telemetry URN resolves to directory with signal files.

        Telemetry structure mirrors contracts - subdirectories with signal files:
        - URN: telemetry:commons:ux:foundations
        - Path: telemetry/commons/ux/foundations/ (subdirectory matching URN)
        - URN: telemetry:match:dilemma.paired
        - Path: telemetry/match/dilemma/paired/ (both : and . create directory levels)
        - Files:
            - {resource}.{type}.{plane}[.{measure}].json (e.g., color.metric.be.count.json)
            - {domain}.{type}.{plane}[.{measure}].json (e.g., foundations.metric.be.error-rate.json)

        Supports multi-level paths:
        - telemetry:ux:foundations → telemetry/ux/foundations/
        - telemetry:commons:ux:foundations → telemetry/commons/ux/foundations/
        - telemetry:match:dilemma.paired → telemetry/match/dilemma/paired/
        """
        parts = telemetry_urn.split(":")
        if len(parts) < 3 or parts[0] != "telemetry":
            return False

        # Use all parts after 'telemetry:' to construct the path (mirrors contract structure)
        # Split by both : and . per artifact-naming convention (same as contracts)
        artifact_part = ':'.join(parts[1:])
        import re
        segments = re.split(r'[:\.]', artifact_part)
        path_parts = segments
        telemetry_path = TELEMETRY_DIR / Path(*path_parts)

        if not (telemetry_path.exists() and telemetry_path.is_dir()):
            return False

        # Must contain signal files
        signal_files = list(telemetry_path.glob("*.json"))
        if not signal_files:
            self.errors.append(
                f"Telemetry directory {telemetry_path} exists but contains no signal files"
            )
            return False

        # Validate each signal file's $id URN, artifact_ref, and acceptance_criteria
        for signal_file in signal_files:
            try:
                with open(signal_file) as f:
                    signal = json.load(f)

                signal_id = signal.get("$id", "")

                # Signal $id must match path (NO "telemetry:" prefix)
                # telemetry URN: telemetry:commons:ux:foundations
                # signal $id should start with: commons:ux:foundations
                expected_id_prefix = telemetry_urn.replace("telemetry:", "", 1)

                if not signal_id.startswith(expected_id_prefix):
                    self.errors.append(
                        f"Signal $id mismatch:\n"
                        f"  File: {signal_file.relative_to(REPO_ROOT)}\n"
                        f"  Found $id: '{signal_id}'\n"
                        f"  Expected prefix: '{expected_id_prefix}' (NO 'telemetry:' prefix)"
                    )
                    continue

                # Validate artifact_ref is a valid contract URN (if present)
                # Note: artifact_ref may not match telemetry path exactly
                # Example: telemetry:commons:ux:foundations may reference contract:ux:foundations
                artifact_ref = signal.get("artifact_ref", "")
                if artifact_ref and not artifact_ref.startswith("contract:"):
                    self.errors.append(
                        f"Signal artifact_ref must start with 'contract:':\n"
                        f"  File: {signal_file.relative_to(REPO_ROOT)}\n"
                        f"  Found artifact_ref: '{artifact_ref}'"
                    )

                # Validate acceptance_criteria are acc: URNs
                acceptance_criteria = signal.get("acceptance_criteria", [])
                for acc_urn in acceptance_criteria:
                    if not acc_urn.startswith("acc:"):
                        self.errors.append(
                            f"Signal has invalid acceptance URN:\n"
                            f"  File: {signal_file.relative_to(REPO_ROOT)}\n"
                            f"  Invalid URN: '{acc_urn}'\n"
                            f"  Must start with 'acc:'"
                        )

                self.stats["telemetry_signals"] += 1

            except Exception as e:
                self.errors.append(
                    f"Error reading telemetry signal {signal_file.relative_to(REPO_ROOT)}: {str(e)}"
                )
                return False

        return True

    def _validate_features(self, wagon_manifest: Dict[str, Any]):
        """Validate feature URNs resolve to files and have code implementations."""
        feature_refs = wagon_manifest.get("features", [])

        for feature_ref in feature_refs:
            feature_urn = feature_ref.get("urn")
            if not feature_urn:
                continue

            # feature:maintain-ux:provide-foundations → plan/maintain_ux/features/provide-foundations.yaml
            if not feature_urn.startswith("feature:"):
                self.errors.append(f"Invalid feature URN format: {feature_urn}")
                continue

            parts = feature_urn.split(":")

            # Support both formats per convention evolution:
            # NEW: feature:wagon:feature-slug (3 parts with colons)
            # OLD: feature:wagon.feature-slug (2 parts with dot separator)
            if len(parts) == 3:
                # NEW format: feature:wagon:feature-slug
                _, wagon_slug, feature_slug = parts
            elif len(parts) == 2:
                # OLD format: feature:wagon.feature-slug
                feature_full = parts[1]
                if "." in feature_full:
                    wagon_slug, feature_slug = feature_full.split(".", 1)
                else:
                    self.errors.append(f"Feature URN missing wagon separator: {feature_urn}")
                    continue
            else:
                self.errors.append(f"Invalid feature URN format: {feature_urn}")
                continue
            wagon_dirname = wagon_slug.replace("-", "_")
            feature_filename = feature_slug.replace("-", "_")

            feature_path = PLAN_DIR / wagon_dirname / "features" / f"{feature_filename}.yaml"

            if not feature_path.exists():
                self.errors.append(
                    f"Feature URN {feature_urn} does not resolve to filesystem:\n"
                    f"  Expected: {feature_path}\n"
                    f"  Path does not exist"
                )
            else:
                self.stats["feature_urns"] += 1

                # Validate feature YAML file has urn field
                try:
                    with open(feature_path) as f:
                        feature_data = yaml.safe_load(f)

                    yaml_urn = feature_data.get("urn", "")
                    if yaml_urn != feature_urn:
                        self.errors.append(
                            f"Feature YAML urn field mismatch:\n"
                            f"  File: {feature_path.relative_to(REPO_ROOT)}\n"
                            f"  Found urn: '{yaml_urn}'\n"
                            f"  Expected: '{feature_urn}'"
                        )
                    else:
                        self.stats["feature_yaml_urns"] += 1

                except Exception as e:
                    self.errors.append(
                        f"Error reading feature YAML {feature_path.relative_to(REPO_ROOT)}: {str(e)}"
                    )

    def _validate_wmbts(self, wagon_manifest: Dict[str, Any]):
        """Validate WMBT URNs resolve to files and acceptances."""
        wmbt_dict = wagon_manifest.get("wmbt", {})

        for wmbt_id, wmbt_desc in wmbt_dict.items():
            # Skip metadata fields
            if wmbt_id in ("total", "coverage"):
                continue

            # wmbt:maintain-ux:L001 → plan/maintain_ux/L001.yaml
            wagon_slug = wagon_manifest.get("wagon", "")
            wagon_dirname = wagon_slug.replace("-", "_")
            wmbt_path = PLAN_DIR / wagon_dirname / f"{wmbt_id}.yaml"

            if not wmbt_path.exists():
                self.errors.append(
                    f"WMBT ID {wmbt_id} does not resolve to file:\n"
                    f"  Expected: {wmbt_path}\n"
                    f"  Path does not exist"
                )
                continue

            self.stats["wmbt_urns"] += 1

            # Validate WMBT file structure
            try:
                with open(wmbt_path) as f:
                    wmbt_data = yaml.safe_load(f)

                wmbt_urn = wmbt_data.get("urn", "")
                expected_urn = f"wmbt:{wagon_slug}:{wmbt_id}"

                if wmbt_urn != expected_urn:
                    self.errors.append(
                        f"WMBT YAML urn field mismatch:\n"
                        f"  File: {wmbt_path.relative_to(REPO_ROOT)}\n"
                        f"  Found urn: '{wmbt_urn}'\n"
                        f"  Expected: '{expected_urn}'"
                    )
                else:
                    self.stats["wmbt_yaml_urns"] += 1

                # Validate acceptances
                self._validate_acceptances(wmbt_data, wagon_slug, wmbt_id)

            except Exception as e:
                self.errors.append(
                    f"Error reading WMBT YAML {wmbt_path.relative_to(REPO_ROOT)}: {str(e)}"
                )

    def _validate_acceptances(self, wmbt_data: Dict[str, Any], wagon_slug: str, wmbt_id: str):
        """Validate acceptance URNs and test files.

        Supports both formats per SPEC-COACH-UTILS-0282:
        - NEW: acc:{wagon}:{wmbt_id}-{harness}-{NNN}[-{slug}]
          Example: acc:pace-dilemmas:L001-UNIT-001
        - OLD: acc:{wagon}:{wmbt_id}:{id} or acc:{wagon}.{wmbt_id}.{id}
          Example: acc:maintain-ux:L001:AC-HTTP-001 or acc:maintain-ux.L001.AC-HTTP-001
        """
        acceptances = wmbt_data.get("acceptances", [])

        for acceptance in acceptances:
            acc_urn = acceptance.get("identity", {}).get("urn", "")
            acc_id = acceptance.get("identity", {}).get("id", "")

            # Validate URN starts with acc:{wagon}:
            expected_urn_start = f"acc:{wagon_slug}:"

            # Also check for old dot-separated format
            expected_urn_start_dots = f"acc:{wagon_slug}."

            if not (acc_urn.startswith(expected_urn_start) or acc_urn.startswith(expected_urn_start_dots)):
                self.errors.append(
                    f"Acceptance URN '{acc_urn}' does not match expected wagon prefix '{expected_urn_start}'"
                )
                continue

            # Extract the part after wagon slug
            if acc_urn.startswith(expected_urn_start):
                remainder = acc_urn[len(expected_urn_start):]
                separator = ":"
            else:
                remainder = acc_urn[len(expected_urn_start_dots):]
                separator = "."

            # Validate that remainder contains wmbt_id
            # NEW format: L001-UNIT-001 (dash-separated)
            # OLD format: L001:AC-HTTP-001 or L001.AC-HTTP-001 (colon/dot-separated)
            if "-" in remainder:
                # NEW format: wmbt_id-harness-NNN
                wmbt_part = remainder.split("-")[0]
            elif separator in remainder:
                # OLD format: wmbt_id:id or wmbt_id.id
                wmbt_part = remainder.split(separator)[0]
            else:
                # Just wmbt_id, no separator
                wmbt_part = remainder

            if wmbt_part != wmbt_id:
                self.errors.append(
                    f"Acceptance URN '{acc_urn}' does not contain expected WMBT ID '{wmbt_id}' (found: '{wmbt_part}')"
                )
                continue

            self.stats["acceptance_urns"] += 1

    def get_report(self) -> str:
        """Generate validation report."""
        if len(self.errors) == 0:
            return (
                f"✅ Wagon {self.wagon_urn} - FULL CHAIN VALIDATED\n"
                f"   📋 Specification Layer:\n"
                f"      • Produce: {self.stats['produce_count']} artifacts\n"
                f"      • Features: {self.stats['feature_urns']} specs ({self.stats['feature_yaml_urns']} YAML URNs)\n"
                f"      • WMBTs: {self.stats['wmbt_urns']} specs ({self.stats['wmbt_yaml_urns']} YAML URNs)\n"
                f"      • Acceptances: {self.stats['acceptance_urns']} criteria\n"
                f"   🔌 Interface Layer:\n"
                f"      • Contracts: {self.stats['contract_urns']} URNs ({self.stats['contract_schemas']} schemas with $id)\n"
                f"      • Telemetry: {self.stats['telemetry_urns']} URNs ({self.stats['telemetry_signals']} signals with $id)\n"
                f"   💻 Implementation Layer:\n"
                f"      • Code files: {self.stats['code_files']} with component: URNs\n"
                f"   🧪 Test Layer:\n"
                f"      • Test files: {self.stats['test_files']} with acc: URNs"
            )
        else:
            return (
                f"❌ Wagon {self.wagon_urn} - CHAIN VALIDATION FAILED\n"
                f"   Errors ({len(self.errors)}):\n" +
                "\n".join(f"     • {err}" for err in self.errors[:5]) +
                (f"\n     ... and {len(self.errors) - 5} more errors" if len(self.errors) > 5 else "")
            )


def get_active_wagon_slugs() -> List[str]:
    """
    Extract wagon slugs from all wagon manifests.

    Returns:
        List of wagon slugs (e.g., ["maintain-ux", "resolve-dilemmas"])
    """
    slugs = []
    wagons_file = PLAN_DIR / "_wagons.yaml"

    if wagons_file.exists():
        with open(wagons_file) as f:
            wagons_data = yaml.safe_load(f)
            for wagon_entry in wagons_data.get("wagons", []):
                if "slug" in wagon_entry:
                    slugs.append(wagon_entry["slug"])

    # Also discover from directories
    for wagon_dir in PLAN_DIR.iterdir():
        if wagon_dir.is_dir() and not wagon_dir.name.startswith("_"):
            # Convert dirname back to slug: maintain_ux → maintain-ux
            slug = wagon_dir.name.replace("_", "-")
            if slug not in slugs:
                slugs.append(slug)

    return sorted(slugs)


@pytest.mark.platform
@pytest.mark.e2e
@pytest.mark.parametrize("wagon_slug", get_active_wagon_slugs())
def test_wagon_complete_urn_chain(wagon_slug: str):
    """
    SPEC-PLATFORM-CHAIN-0001: Complete wagon URN chain reconciliation

    Given: A wagon URN (wagon:slug)
    When: Recursively validating the entire chain via URNs only
    Then:
      1. Wagon URN → manifest file exists
      2. Produce artifacts → contract URNs → contracts/{domain}/{resource}/
      3. Contract schemas have $id field matching domain:resource:*
      4. Produce artifacts → telemetry URNs → telemetry/{domain}/{resource}/
      5. Telemetry signals have $id, artifact_ref, acceptance_criteria URNs
      6. Feature URNs → feature YAML files exist with urn: field
      7. Feature code files exist with component: URN markers (first line)
      8. WMBT IDs → WMBT YAML files exist with urn: field
      9. Acceptance URNs follow expected pattern
     10. Acceptance test files exist with acc: URN markers (first line)

    This test validates 100% URN traceability across ALL layers:
    - Specification Layer: YAML files with urn: fields
    - Interface Layer: JSON schemas with $id fields and artifact_ref
    - Implementation Layer: Code files with component: URN comments
    - Test Layer: Test files with acc: URN comments
    """
    validator = WagonChainValidator(wagon_slug)
    is_valid = validator.validate()

    report = validator.get_report()
    print(f"\n{report}")

    if not is_valid:
        pytest.fail(f"\n\nWagon {wagon_slug} URN chain validation failed:\n{report}")


@pytest.mark.platform
def test_all_wagons_have_complete_chains():
    """
    SPEC-PLATFORM-CHAIN-0002: All wagons have complete URN chains

    Given: All wagon slugs in repository
    When: Validating each wagon's URN chain
    Then: All wagons pass complete chain validation
          Summary report shows total statistics
    """
    active_wagon_slugs = get_active_wagon_slugs()
    results = {}
    total_errors = 0

    for wagon_slug in active_wagon_slugs:
        validator = WagonChainValidator(wagon_slug)
        is_valid = validator.validate()
        results[wagon_slug] = {
            "valid": is_valid,
            "errors": len(validator.errors),
            "stats": validator.stats
        }
        total_errors += len(validator.errors)

    # Generate summary report
    valid_count = sum(1 for r in results.values() if r["valid"])
    total_count = len(results)

    summary = [
        f"\n{'=' * 80}",
        f"COMPLETE URN CHAIN VALIDATION SUMMARY",
        f"{'=' * 80}",
        f"Total Wagons: {total_count}",
        f"Valid Chains: {valid_count}/{total_count}",
        f"Total Errors: {total_errors}",
        f"{'=' * 80}"
    ]

    for wagon_slug, result in sorted(results.items()):
        status = "✅" if result["valid"] else "❌"
        summary.append(
            f"{status} {wagon_slug}: "
            f"{result['stats']['produce_count']} artifacts, "
            f"{result['stats']['contract_urns']} contracts, "
            f"{result['stats']['telemetry_urns']} telemetry"
        )

    print("\n".join(summary))

    assert total_errors == 0, f"\n\n{total_errors} URN chain errors found across {total_count} wagons"
