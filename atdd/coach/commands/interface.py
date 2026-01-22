#!/usr/bin/env python3
"""
Producer-Contract Traceability Validator

Validates bidirectional traceability between wagon produce declarations
and contract schemas, following artifact naming conventions.

Features:
- Scans wagon/feature produce declarations
- Validates contract schemas against meta-schema
- Checks producer/consumer relationships
- Generates missing contract schemas (with --fix)
- Reports orphaned contracts without producers
"""

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional
import yaml
import json
from jsonschema import Draft7Validator
from dataclasses import dataclass, field

REPO_ROOT = Path(__file__).parent.parent.parent.parent
PLAN_DIR = REPO_ROOT / "plan"
CONTRACTS_DIR = REPO_ROOT / "contracts"
ARTIFACT_SCHEMA_PATH = REPO_ROOT / ".claude/schemas/tester/artifact.schema.json"
MANIFEST_FILE = REPO_ROOT / "manifest.yaml"
REGISTRY_FILE = REPO_ROOT / "plan/_wagons.yaml"


@dataclass
class ProduceDeclaration:
    """Represents a produce declaration from a wagon/feature"""
    wagon_slug: str
    wagon_theme: str
    artifact_name: str
    contract_urn: Optional[str]
    source_file: Path
    source_type: str  # 'wagon' or 'feature'


@dataclass
class ContractSchema:
    """Represents a contract schema file"""
    file_path: Path
    schema_id: str
    domain: str
    resource: str
    producer: Optional[str]
    consumers: List[str]
    valid: bool
    validation_errors: List[str] = field(default_factory=list)


class ProducerValidator:
    """Validates producer-contract traceability and generates missing contracts"""

    def __init__(self, auto_fix: bool = False, verbose: bool = False):
        self.auto_fix = auto_fix
        self.verbose = verbose
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.produce_declarations: List[ProduceDeclaration] = []
        self.contract_schemas: List[ContractSchema] = []
        self.artifact_schema = None
        self.wagon_registry = set()
        self.draft_wagons = set()

    def load_wagon_registry(self):
        """Load active and draft wagons from registry"""
        try:
            with open(REGISTRY_FILE) as f:
                registry_data = yaml.safe_load(f)

            wagons = registry_data.get("wagons", [])

            # Handle both list and dict formats
            if isinstance(wagons, list):
                for wagon_data in wagons:
                    status = wagon_data.get("status", "active")
                    slug = wagon_data.get("wagon", "")

                    if status == "active":
                        self.wagon_registry.add(slug)
                    elif status == "draft":
                        self.draft_wagons.add(slug)
            elif isinstance(wagons, dict):
                for wagon_data in wagons.values():
                    status = wagon_data.get("status", "active")
                    slug = wagon_data.get("slug", wagon_data.get("wagon", ""))

                    if status == "active":
                        self.wagon_registry.add(slug)
                    elif status == "draft":
                        self.draft_wagons.add(slug)

        except FileNotFoundError:
            self.warnings.append(f"Registry file not found: {REGISTRY_FILE}")
        except Exception as e:
            self.errors.append(f"Error loading wagon registry: {e}")

    def load_artifact_schema(self):
        """Load the artifact meta-schema for validation"""
        try:
            with open(ARTIFACT_SCHEMA_PATH) as f:
                self.artifact_schema = json.load(f)
        except Exception as e:
            self.errors.append(f"Error loading artifact schema: {e}")

    def scan_wagons(self):
        """Scan all wagon manifests for produce declarations"""
        wagon_files = list(PLAN_DIR.glob("*/_*.yaml"))

        if self.verbose:
            print(f"  Scanning {len(wagon_files)} wagon manifests...")

        for wagon_file in wagon_files:
            try:
                with open(wagon_file) as f:
                    wagon_data = yaml.safe_load(f)

                wagon_slug = wagon_data.get("wagon")
                wagon_theme = wagon_data.get("theme", "unknown")

                # Check if wagon is in registry or draft
                if wagon_slug not in self.wagon_registry and wagon_slug not in self.draft_wagons:
                    if self.verbose:
                        print(f"    Note: {wagon_slug} not in registry (will still scan)")

                # Get produce declarations
                produce_items = wagon_data.get("produce", [])
                for item in produce_items:
                    artifact_name = item.get("name")
                    contract_urn = item.get("contract")

                    if artifact_name:
                        self.produce_declarations.append(ProduceDeclaration(
                            wagon_slug=wagon_slug,
                            wagon_theme=wagon_theme,
                            artifact_name=artifact_name,
                            contract_urn=contract_urn,
                            source_file=wagon_file,
                            source_type="wagon"
                        ))
            except Exception as e:
                self.errors.append(f"Error reading wagon {wagon_file.name}: {e}")

    def scan_features(self):
        """Scan feature files for produce declarations"""
        feature_files = list(PLAN_DIR.glob("*/features/**/*.yaml"))

        if self.verbose:
            print(f"  Scanning {len(feature_files)} feature files...")

        for feature_file in feature_files:
            try:
                with open(feature_file) as f:
                    feature_data = yaml.safe_load(f)

                # Extract wagon from feature URN
                feature_urn = feature_data.get("urn", "")
                # urn format: feature:wagon-slug:feature-name
                parts = feature_urn.split(":")
                if len(parts) >= 2:
                    wagon_slug = parts[1]
                else:
                    continue

                # Determine wagon theme
                wagon_theme = self._get_wagon_theme(wagon_slug)

                # Get produces from feature
                produces = feature_data.get("produces", [])
                for item in produces:
                    artifact_name = item.get("name")
                    contract_urn = item.get("contract")

                    if artifact_name:
                        self.produce_declarations.append(ProduceDeclaration(
                            wagon_slug=wagon_slug,
                            wagon_theme=wagon_theme,
                            artifact_name=artifact_name,
                            contract_urn=contract_urn,
                            source_file=feature_file,
                            source_type="feature"
                        ))
            except Exception as e:
                self.errors.append(f"Error reading feature {feature_file.name}: {e}")

    def _get_wagon_theme(self, wagon_slug: str) -> str:
        """Get theme for a wagon"""
        wagon_dir = wagon_slug.replace("-", "_")
        wagon_file = PLAN_DIR / wagon_dir / f"_{wagon_dir}.yaml"

        if wagon_file.exists():
            try:
                with open(wagon_file) as f:
                    wagon_data = yaml.safe_load(f)
                    return wagon_data.get("theme", "unknown")
            except:
                pass

        return "unknown"

    def scan_contracts(self):
        """Scan all contract schema files"""
        contract_files = list(CONTRACTS_DIR.glob("**/*.schema.json"))

        if self.verbose:
            print(f"  Scanning {len(contract_files)} contract schemas...")

        for contract_file in contract_files:
            try:
                with open(contract_file) as f:
                    schema = json.load(f)

                schema_id = schema.get("$id", "")
                metadata = schema.get("x-artifact-metadata", {})

                domain = metadata.get("domain", "")
                resource = metadata.get("resource", "")
                producer = metadata.get("producer")
                consumers = metadata.get("consumers", [])

                # Validate against meta-schema
                valid = True
                validation_errors = []

                if self.artifact_schema:
                    validator = Draft7Validator(self.artifact_schema)
                    errors = list(validator.iter_errors(schema))
                    if errors:
                        valid = False
                        validation_errors = [e.message for e in errors]

                self.contract_schemas.append(ContractSchema(
                    file_path=contract_file,
                    schema_id=schema_id,
                    domain=domain,
                    resource=resource,
                    producer=producer,
                    consumers=consumers,
                    valid=valid,
                    validation_errors=validation_errors
                ))

            except json.JSONDecodeError as e:
                self.errors.append(f"Invalid JSON in {contract_file.name}: {e}")
            except Exception as e:
                self.errors.append(f"Error reading contract {contract_file.name}: {e}")

    def validate_bidirectional_traceability(self):
        """Check produce → contract and contract → produce traceability"""

        # Check produce → contract (missing contracts)
        missing_contracts = []
        for prod in self.produce_declarations:
            if prod.contract_urn and prod.contract_urn != "null":
                expected_path = self._resolve_contract_urn_to_path(prod.contract_urn)

                if expected_path and not expected_path.exists():
                    missing_contracts.append((prod, expected_path))
                    self.warnings.append(
                        f"Missing contract for wagon:{prod.wagon_slug}:\n"
                        f"  Artifact: {prod.artifact_name}\n"
                        f"  Contract URN: {prod.contract_urn}\n"
                        f"  Expected: {expected_path.relative_to(REPO_ROOT)}\n"
                        f"  Source: {prod.source_file.relative_to(REPO_ROOT)} ({prod.source_type})"
                    )

        # Check contract → produce (orphaned contracts)
        for contract in self.contract_schemas:
            if not contract.producer:
                self.warnings.append(
                    f"Contract missing producer field:\n"
                    f"  File: {contract.file_path.relative_to(REPO_ROOT)}\n"
                    f"  Schema ID: {contract.schema_id}"
                )
                continue

            # Find matching produce declaration
            wagon_slug = contract.producer.replace("wagon:", "")
            found = False

            for prod in self.produce_declarations:
                if prod.wagon_slug == wagon_slug:
                    # Check if contract URN matches or file matches
                    if prod.contract_urn:
                        expected_path = self._resolve_contract_urn_to_path(prod.contract_urn)
                        if expected_path == contract.file_path:
                            found = True
                            break

            if not found:
                # Check if wagon exists (active or draft)
                if wagon_slug in self.wagon_registry or wagon_slug in self.draft_wagons:
                    self.warnings.append(
                        f"Contract has producer but no matching produce declaration:\n"
                        f"  File: {contract.file_path.relative_to(REPO_ROOT)}\n"
                        f"  Producer: {contract.producer}\n"
                        f"  Schema ID: {contract.schema_id}\n"
                        f"  Note: Wagon {wagon_slug} exists but doesn't declare this artifact"
                    )
                else:
                    self.errors.append(
                        f"Contract references unknown wagon:\n"
                        f"  File: {contract.file_path.relative_to(REPO_ROOT)}\n"
                        f"  Producer: {contract.producer}\n"
                        f"  Wagon not found in registry or plan/"
                    )

        return missing_contracts

    def _resolve_contract_urn_to_path(self, contract_urn: str) -> Optional[Path]:
        """Convert contract URN to file path using NEW naming convention

        NEW CONVENTION:
          contract:commons:player.identity → contracts/commons/player/identity.schema.json
          contract:mechanic:decision.choice → contracts/mechanic/decision/choice.schema.json
          contract:sensory:gesture.tapped → contracts/sensory/gesture/tapped.schema.json

        Pattern: contract:{theme}:{domain}.{facet} → contracts/{theme}/{domain}/{facet}.schema.json

        LEGACY SUPPORT:
          contract:system:identifiers.username → contracts/system/identifiers/username.schema.json
          contract:player:identity → contracts/player/identity.schema.json
        """
        if not contract_urn or contract_urn == "null" or not contract_urn.startswith("contract:"):
            return None

        # Remove "contract:" prefix: contract:commons:player.identity → commons:player.identity
        urn_without_prefix = contract_urn[9:]

        # Split by colon: commons:player.identity → ['commons', 'player.identity']
        parts = urn_without_prefix.split(":")

        if len(parts) < 2:
            return None

        # First part is theme/namespace
        theme = parts[0]

        # Remaining parts form domain.facet
        domain_facet = ":".join(parts[1:])

        # Convert domain.facet to domain/facet path
        # player.identity → player/identity
        # decision.choice → decision/choice
        # identifiers.username → identifiers/username
        path_parts = domain_facet.replace(".", "/")

        # Build final path: contracts/{theme}/{domain}/{facet}.schema.json
        return CONTRACTS_DIR / theme / f"{path_parts}.schema.json"

    def validate_contract_schemas(self):
        """Report schema validation errors"""
        invalid_contracts = [c for c in self.contract_schemas if not c.valid]

        if invalid_contracts:
            for contract in invalid_contracts:
                # Only show first 3 errors to avoid overwhelming output
                error_summary = contract.validation_errors[:3]
                if len(contract.validation_errors) > 3:
                    error_summary.append(f"... and {len(contract.validation_errors) - 3} more errors")

                self.errors.append(
                    f"Invalid contract schema: {contract.file_path.relative_to(REPO_ROOT)}\n" +
                    "\n".join(f"  - {err}" for err in error_summary)
                )

    def generate_missing_contracts(self, missing_contracts: List[Tuple[ProduceDeclaration, Path]]):
        """Generate contract schemas for produce declarations without contracts"""
        if not self.auto_fix or not missing_contracts:
            return

        print(f"\n🔧 Generating {len(missing_contracts)} missing contracts...")

        for prod, file_path in missing_contracts:
            try:
                self._generate_contract_schema(prod, file_path)
                print(f"  ✅ {file_path.relative_to(REPO_ROOT)}")
            except Exception as e:
                self.errors.append(f"Failed to generate {file_path.name}: {e}")

    def _generate_contract_schema(self, prod: ProduceDeclaration, file_path: Path):
        """Generate a contract schema template following NEW artifact naming conventions

        NEW CONVENTION:
          Artifact name: commons:player.identity (theme:domain.facet)
          Contract URN: contract:commons:player.identity
          Schema $id: urn:contract:commons:player.identity (current) or commons:player.identity:v1 (spec)
          File path: contracts/commons/player/identity.schema.json
        """

        # Parse artifact name: {theme}:{domain}.{facet}
        # Examples: commons:player.identity, mechanic:decision.choice
        artifact_parts = prod.artifact_name.split(":", 1)

        if len(artifact_parts) >= 2:
            theme = artifact_parts[0]
            domain_facet = artifact_parts[1]

            # Split domain.facet
            if "." in domain_facet:
                domain, facet = domain_facet.split(".", 1)
            else:
                domain = domain_facet
                facet = domain_facet

            resource = domain_facet  # Keep as is: player.identity
        else:
            # Fallback if no theme prefix
            theme = prod.wagon_theme
            domain = prod.artifact_name
            facet = prod.artifact_name
            resource = prod.artifact_name

        # Generate schema $id following contract.convention.yaml
        # Format: {theme}:{resource} (NO version suffix)
        # Example: commons:player.identity, ux:foundations
        schema_id = f"{theme}:{resource}"

        # Determine API path from domain.facet
        # player.identity → /player/identity
        api_path = "/" + resource.replace(".", "/")

        # Infer HTTP method based on REST best practices
        http_method = self._infer_http_method(prod.artifact_name, resource)

        # Generate title
        title = self._titlecase(f"{theme} {resource}") + " Contract"

        # Build API operations array per contract.convention.yaml
        # Build responses based on method
        success_code = "200" if http_method == "GET" else "201"
        responses = {
            success_code: {
                "description": "Success",
                "schema": f"$ref: #/definitions/{self._titlecase(resource).replace(' ', '')}"
            },
            "400": {
                "description": "Bad Request"
            }
        }

        # Add method-specific error responses
        if http_method == "GET":
            responses["404"] = {"description": "Not Found"}
        else:
            responses["500"] = {"description": "Internal Server Error"}

        operations = [
            {
                "method": http_method,
                "path": api_path,
                "description": f"{'Retrieve' if http_method == 'GET' else 'Submit'} {resource}",
                "responses": responses,
                "idempotent": http_method in ["GET", "PUT", "DELETE"]
            }
        ]

        # Add request body for non-GET operations
        if http_method != "GET":
            operations[0]["requestBody"] = {
                "schema": f"$ref: #/definitions/{self._titlecase(resource).replace(' ', '')}",
                "required": True,
                "contentType": "application/json"
            }

        # Build traceability per contract.convention.yaml (REQUIRED)
        wagon_dir = prod.wagon_slug.replace("-", "_")
        traceability = {
            "wagon_ref": f"plan/{wagon_dir}/_{wagon_dir}.yaml",
            "feature_refs": [f"feature:{prod.wagon_slug}:TODO"],  # Placeholder
            "acceptance_refs": []
        }

        # Build testing metadata per contract.convention.yaml (REQUIRED)
        testing = {
            "directory": f"contracts/{theme}/{domain}/tests/",
            "schema_tests": [f"{facet}_schema_test.json"]
        }

        # Generate schema with versioning per contract.convention.yaml
        # New contracts start at v1.0.0 with status="draft"
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": schema_id,
            "version": "1.0.0",
            "title": title,
            "description": f"Contract schema for {prod.artifact_name} artifact",
            "type": "object",
            "properties": {
                "_version": {
                    "type": "string",
                    "description": "Contract version for backward compatibility handling. Default '1' for v1.x data.",
                    "default": "1"
                }
            },
            "required": [],
            "x-artifact-metadata": {
                "domain": domain,
                "resource": resource,
                "version": "1.0.0",
                "producer": f"wagon:{prod.wagon_slug}",
                "consumers": [],
                "dependencies": [],
                "api": {
                    "version": "v1",
                    "operations": operations
                },
                "traceability": traceability,
                "testing": testing,
                "governance": {
                    "status": "draft",
                    "stability": "experimental"
                }
            }
        }

        # Create directory if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write schema
        with open(file_path, 'w') as f:
            json.dump(schema, f, indent=2)
            f.write('\n')  # Add trailing newline

    def _titlecase(self, text: str) -> str:
        """Convert kebab-case or dot notation to Title Case"""
        return " ".join(word.capitalize() for word in text.replace("-", " ").replace("_", " ").replace(".", " ").split())

    def _infer_http_method(self, artifact_name: str, resource: str) -> str:
        """Infer HTTP method based on REST best practices

        Rules:
        - GET: Retrieve state/data (identity, config, remaining, final, etc.)
        - POST: Create/submit/trigger (choice, registered, started, agreement, etc.)
        - PUT: Update entire resource
        - PATCH: Partial update
        - DELETE: Remove resource

        Examples:
          commons:player.identity → GET (retrieve identity)
          mechanic:decision.choice → POST (submit choice)
          match:score.final → GET (retrieve final score)
          commons:account:registered → POST (registration event)
        """
        # Extract facet from resource (last part after dot)
        facet = resource.split(".")[-1] if "." in resource else resource

        # GET patterns - retrieving state or data (nouns/adjectives)
        get_patterns = [
            "identity", "identities",
            "claims",
            "config", "configuration",
            "remaining", "exhausted",
            "final", "score",
            "result", "results",
            "current", "active",  # State queries (not events)
            "impact",
            "evaluation-score", "evaluation",
            "manifest", "catalog",
            "foundations", "primitives", "components", "templates",
            "audio", "animation", "haptics", "themes", "fallback",
            "fragments", "fragment",
            "data", "stream",
            "raw", "presentation", "layer",
            "profile", "personas"
        ]

        # POST patterns - creating, submitting, triggering events (verbs/past participles)
        post_patterns = [
            "choice", "decision",
            "registered", "registration",
            "terminated", "termination",
            "started", "finished", "paused", "resumed",
            "committed", "updated", "changed",  # State transition events
            "succeeded", "failed",  # Outcome events
            "closed", "opened",  # Session events
            "turn-started", "turn-ended",
            "agreement", "agreements",
            "mapping", "attribution",
            "rephrased",
            "new", "create", "created",
            "paired",
            "uuid", "username"  # Generators
        ]

        # Check facet against patterns
        facet_lower = facet.lower()

        if any(pattern in facet_lower for pattern in get_patterns):
            return "GET"
        elif any(pattern in facet_lower for pattern in post_patterns):
            return "POST"

        # Default heuristics based on common patterns
        if facet_lower.endswith(("ed", "ing")):  # Past tense or gerund = event
            return "POST"
        elif facet_lower.endswith(("s", "list", "collection")):  # Plural = list
            return "GET"

        # Default to GET for unknown patterns (prefer idempotent operations)
        return "GET"

    def run(self) -> bool:
        """Run full validation"""
        print("🔍 Producer-Contract Traceability Validation")
        print("=" * 80)

        print("\n📋 Loading wagon registry...")
        self.load_wagon_registry()
        print(f"  Active wagons: {len(self.wagon_registry)}")
        print(f"  Draft wagons: {len(self.draft_wagons)}")

        print("\n🔍 Scanning produce declarations...")
        self.load_artifact_schema()
        self.scan_wagons()
        self.scan_features()
        print(f"  Found {len(self.produce_declarations)} produce declarations")

        print("\n🔍 Scanning contract schemas...")
        self.scan_contracts()
        print(f"  Found {len(self.contract_schemas)} contract schemas")

        print("\n🔍 Validating contract schemas against meta-schema...")
        self.validate_contract_schemas()

        print("\n🔍 Validating bidirectional traceability...")
        missing_contracts = self.validate_bidirectional_traceability()

        if self.auto_fix and missing_contracts:
            self.generate_missing_contracts(missing_contracts)

        # Print summary
        print("\n" + "=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)

        stats = {
            "produce_declarations": len(self.produce_declarations),
            "contract_schemas": len(self.contract_schemas),
            "valid_contracts": len([c for c in self.contract_schemas if c.valid]),
            "invalid_contracts": len([c for c in self.contract_schemas if not c.valid]),
            "missing_contracts": len(missing_contracts) if not self.auto_fix else 0,
            "orphaned_contracts": len([w for w in self.warnings if "no matching produce" in w]),
        }

        print(f"\n📊 Statistics:")
        print(f"  Produce declarations: {stats['produce_declarations']}")
        print(f"  Contract schemas: {stats['contract_schemas']}")
        print(f"  Valid contracts: {stats['valid_contracts']}")
        print(f"  Invalid contracts: {stats['invalid_contracts']}")
        if not self.auto_fix:
            print(f"  Missing contracts: {stats['missing_contracts']}")
        print(f"  Orphaned contracts: {stats['orphaned_contracts']}")

        if self.errors:
            print(f"\n❌ Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"\n{error}")

        if self.warnings:
            print(f"\n⚠️  Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"\n{warning}")

        if not self.errors and not self.warnings:
            print("\n✅ All producer-contract traceability checks passed!")
        elif not self.errors:
            print(f"\n✅ No errors, but {len(self.warnings)} warnings")

        print("\n" + "=" * 80)

        return len(self.errors) == 0


def scaffold_contract_metadata(
    artifact_urn: str,
    plan_dir: Path,
    contracts_dir: Path,
    convention_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Generate complete contract metadata from wagon and feature interfaces.

    Implements SPEC-COACH-UTILS-0294: Parse artifact URN, scan wagon/feature manifests,
    generate complete x-artifact-metadata, and create contract scaffold.

    Args:
        artifact_urn: Artifact URN (e.g. "mechanic:timebank.exhausted")
        plan_dir: Path to plan/ directory containing wagon manifests
        contracts_dir: Path to contracts/ directory
        convention_path: Optional path to artifact-naming.convention.yaml

    Returns:
        Dict with keys: created (bool), path (str), metadata (dict)
    """
    # Parse artifact URN according to artifact-naming.convention.yaml
    # Pattern: theme(category)*aspect(.variant)?
    # Examples: mechanic:timebank.exhausted → theme=mechanic, aspect=timebank, variant=exhausted
    #           commons:ux:foundations:color → theme=commons, categories=[ux,foundations], aspect=color

    parts = artifact_urn.replace(".", ":").split(":")
    theme = parts[0]
    aspect = parts[-1] if len(parts) > 1 else theme

    # Reconstruct with original dot for variant detection
    urn_parts = artifact_urn.split(":")
    has_variant = "." in urn_parts[-1] if urn_parts else False

    if has_variant:
        aspect_variant = urn_parts[-1]
        aspect_base, variant = aspect_variant.split(".", 1)
        resource = aspect_variant
    else:
        aspect_base = urn_parts[-1] if len(urn_parts) > 1 else theme
        variant = None
        resource = artifact_urn.split(":", 1)[1] if ":" in artifact_urn else artifact_urn

    # Convert URN to contract file path
    # mechanic:timebank.exhausted → contracts/mechanic/timebank/exhausted.schema.json
    path_segments = []
    for i, part in enumerate(urn_parts):
        if "." in part and i == len(urn_parts) - 1:
            # Last segment with variant: split by dot
            base, var = part.split(".", 1)
            path_segments.append(base)
            path_segments.append(var)
        else:
            path_segments.append(part)

    contract_path = contracts_dir / "/".join(path_segments[:-1]) / f"{path_segments[-1]}.schema.json"

    # Scan wagon manifests to find producer
    producer_wagon = None
    producer_theme = None
    producer_consume = []
    producer_features = []

    for wagon_file in plan_dir.glob("*/_*.yaml"):
        with open(wagon_file) as f:
            wagon_data = yaml.safe_load(f)

        produce_items = wagon_data.get("produce", [])
        for item in produce_items:
            if item.get("name") == artifact_urn:
                producer_wagon = wagon_data.get("wagon")
                producer_theme = wagon_data.get("theme", "unknown")
                producer_consume = wagon_data.get("consume", [])
                producer_features = wagon_data.get("features", [])
                break

        if producer_wagon:
            break

    # Scan all wagons to find consumers
    consumers = []
    for wagon_file in plan_dir.glob("*/_*.yaml"):
        with open(wagon_file) as f:
            wagon_data = yaml.safe_load(f)

        wagon_slug = wagon_data.get("wagon")
        consume_items = wagon_data.get("consume", [])

        for item in consume_items:
            if item.get("name") == f"contract:{artifact_urn}":
                consumers.append(f"wagon:{wagon_slug}")
                break

    # Extract dependencies from producer consume[]
    dependencies = [item.get("name") for item in producer_consume if item.get("name")]

    # Infer API method from aspect/variant
    http_method = _infer_http_method_for_scaffold(artifact_urn, aspect_base, variant)

    # Generate API path
    api_path = "/" + "/".join(urn_parts)
    if has_variant:
        api_path = "/" + "/".join(urn_parts[:-1]) + "/" + urn_parts[-1].replace(".", "/")

    # Extract traceability
    wagon_snake = producer_wagon.replace("-", "_") if producer_wagon else "unknown"
    wagon_ref = f"plan/{wagon_snake}/_{wagon_snake}.yaml"
    feature_refs = [f.get("name") for f in producer_features if f.get("name")]

    # Generate testing paths (relative to contracts_dir)
    test_dir_path = contract_path.parent / "tests"
    test_dir = str(test_dir_path.relative_to(contracts_dir.parent)) + "/"
    test_file = f"{path_segments[-1]}_schema_test.json"

    # Build x-artifact-metadata
    # Domain is the base aspect without variant
    # mechanic:timebank.exhausted → domain=timebank, resource=timebank.exhausted
    domain = aspect_base if has_variant else (urn_parts[1] if len(urn_parts) > 1 else theme)

    metadata = {
        "domain": domain,
        "resource": resource,
        "version": "1.0.0",
        "producer": f"wagon:{producer_wagon}" if producer_wagon else "wagon:unknown",
        "consumers": consumers,
        "dependencies": dependencies,
        "api": {
            "operations": [{
                "method": http_method,
                "path": api_path,
                "responses": {
                    "200": {"description": "Success"}
                }
            }]
        },
        "traceability": {
            "wagon_ref": wagon_ref,
            "feature_refs": feature_refs
        },
        "testing": {
            "directory": test_dir,
            "schema_tests": [test_file]
        },
        "governance": {
            "status": "draft",
            "stability": "experimental"
        }
    }

    # Create contract schema - start at v0.1.0 with draft status
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": artifact_urn,
        "version": "1.0.0",
        "title": _titlecase_scaffold(artifact_urn),
        "description": f"Contract schema for {artifact_urn}",
        "type": "object",
        "properties": {
            "_version": {
                "type": "string",
                "description": "Contract version for backward compatibility handling. Default '1' for v1.x data.",
                "default": "1"
            }
        },
        "x-artifact-metadata": metadata
    }

    # Write contract file
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    with open(contract_path, 'w') as f:
        json.dump(schema, f, indent=2)
        f.write('\n')

    return {
        "created": True,
        "path": str(contract_path),
        "metadata": metadata
    }


def _infer_http_method_for_scaffold(urn: str, aspect: str, variant: Optional[str]) -> str:
    """Infer HTTP method from artifact URN patterns"""
    check_term = variant if variant else aspect
    check_term_lower = check_term.lower()

    # Event patterns (POST)
    if any(term in check_term_lower for term in ["exhausted", "started", "ended", "committed", "registered"]):
        return "POST"

    # State patterns (GET)
    if any(term in check_term_lower for term in ["current", "remaining", "config", "state", "identity"]):
        return "GET"

    return "GET"  # Default to GET


def _titlecase_scaffold(text: str) -> str:
    """Convert URN to title case"""
    return " ".join(word.capitalize() for word in text.replace(":", " ").replace(".", " ").split())


def validate_and_update_contract_metadata(
    contract_path: Path,
    plan_dir: Path,
    contracts_dir: Path
) -> Dict[str, Any]:
    """
    Validate and update existing contract metadata completeness.

    Implements SPEC-COACH-UTILS-0295: Re-scan wagon manifests, detect missing/outdated
    fields, update only what's needed, preserve user customizations.

    Args:
        contract_path: Path to existing contract schema file
        plan_dir: Path to plan/ directory
        contracts_dir: Path to contracts/ directory

    Returns:
        Dict with keys: updates (dict), preserved_customizations (int)
    """
    # Read existing contract
    with open(contract_path) as f:
        contract = json.load(f)

    existing_metadata = contract.get("x-artifact-metadata", {})
    artifact_urn = contract.get("$id", "")

    # Re-generate metadata from current wagon state
    regenerated = scaffold_contract_metadata(
        artifact_urn=artifact_urn,
        plan_dir=plan_dir,
        contracts_dir=contracts_dir
    )

    new_metadata = regenerated["metadata"]

    # Compare and update
    updates = {}
    preserved = 0

    # Update consumers if changed
    existing_consumers = set(existing_metadata.get("consumers", []))
    new_consumers = set(new_metadata.get("consumers", []))

    if new_consumers != existing_consumers:
        # Merge: keep existing + add new
        merged_consumers = list(existing_consumers | new_consumers)
        existing_metadata["consumers"] = merged_consumers
        updates["consumers"] = list(new_consumers - existing_consumers)

    # Update missing traceability.feature_refs
    traceability = existing_metadata.get("traceability", {})
    if "feature_refs" not in traceability or not traceability["feature_refs"]:
        traceability["feature_refs"] = new_metadata["traceability"]["feature_refs"]
        existing_metadata["traceability"] = traceability
        updates["traceability.feature_refs"] = new_metadata["traceability"]["feature_refs"]

    # Update missing testing.schema_tests
    testing = existing_metadata.get("testing", {})
    if "schema_tests" not in testing or not testing["schema_tests"]:
        testing["schema_tests"] = new_metadata["testing"]["schema_tests"]
        existing_metadata["testing"] = testing
        updates["testing.schema_tests"] = new_metadata["testing"]["schema_tests"]

    # Count preserved customizations
    if contract.get("description") and "CUSTOM" in contract["description"]:
        preserved += 1

    api_ops = existing_metadata.get("api", {}).get("operations", [])
    if api_ops and api_ops[0].get("description") and "CUSTOM" in api_ops[0]["description"]:
        preserved += 1

    # Write updated contract
    contract["x-artifact-metadata"] = existing_metadata
    with open(contract_path, 'w') as f:
        json.dump(contract, f, indent=2)
        f.write('\n')

    return {
        "updates": updates,
        "preserved_customizations": preserved
    }


def create_placeholder_test_files(
    contract_path: Path,
    contracts_dir: Path
) -> Dict[str, Any]:
    """
    Create placeholder test files for scaffolded contracts.

    Implements SPEC-COACH-UTILS-0296: Create test directory, generate placeholder
    test files, avoid overwriting existing tests.

    Args:
        contract_path: Path to contract schema file
        contracts_dir: Path to contracts/ directory

    Returns:
        Dict with keys: created (int), skipped (int), created_files (list), skipped_files (list)
    """
    # Read contract to get testing metadata
    with open(contract_path) as f:
        contract = json.load(f)

    metadata = contract.get("x-artifact-metadata", {})
    testing = metadata.get("testing", {})

    test_dir_rel = testing.get("directory", "")
    test_files = testing.get("schema_tests", [])

    if not test_dir_rel or not test_files:
        return {
            "created": 0,
            "skipped": 0,
            "created_files": [],
            "skipped_files": []
        }

    # Resolve test directory path
    test_dir = contracts_dir / test_dir_rel.replace("contracts/", "")
    test_dir.mkdir(parents=True, exist_ok=True)

    created_files = []
    skipped_files = []
    artifact_urn = contract.get("$id", "")

    for test_file in test_files:
        test_path = test_dir / test_file

        if test_path.exists():
            skipped_files.append(test_file)
        else:
            # Create placeholder
            placeholder = {
                "description": f"TODO: Implement schema tests for {artifact_urn}",
                "contract": artifact_urn,
                "test_cases": [
                    {
                        "name": "TODO: Add test case",
                        "input": {},
                        "expected": "valid"
                    }
                ]
            }

            with open(test_path, 'w') as f:
                json.dump(placeholder, f, indent=2)
                f.write('\n')

            created_files.append(test_file)

    return {
        "created": len(created_files),
        "skipped": len(skipped_files),
        "created_files": created_files,
        "skipped_files": skipped_files
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate producer-contract traceability and generate missing contracts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate traceability
  python atdd/coach/commands/producer.py

  # Auto-generate missing contracts
  python atdd/coach/commands/producer.py --fix

  # Verbose output
  python atdd/coach/commands/producer.py --verbose
        """
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-generate missing contract schemas"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    validator = ProducerValidator(auto_fix=args.fix, verbose=args.verbose)
    success = validator.run()

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
