"""
Platform tests: Contract schema compliance validation.

Validates that all contract schemas follow the meta-schema and conventions:
- atdd/tester/conventions/contract.convention.yaml
- atdd/planner/conventions/interface.convention.yaml
- atdd/tester/schemas/contract.schema.json (meta-schema)
"""
import pytest
import json
import re
from pathlib import Path
from jsonschema import validate, ValidationError, Draft7Validator

# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS_DIR = REPO_ROOT / "contracts"
PLAN_DIR = REPO_ROOT / "plan"
META_SCHEMA_PATH = REPO_ROOT / "atdd" / "tester" / "schemas" / "contract.schema.json"


@pytest.fixture
def meta_schema():
    """Load contract meta-schema"""
    if not META_SCHEMA_PATH.exists():
        pytest.skip(f"Meta-schema not found: {META_SCHEMA_PATH}")

    with open(META_SCHEMA_PATH) as f:
        return json.load(f)


def find_all_contract_schemas():
    """Find all contract schema files"""
    if not CONTRACTS_DIR.exists():
        return []
    return list(CONTRACTS_DIR.glob("**/*.schema.json"))


def load_plan_acceptance_urns():
    """Collect acceptance URNs from plan/ YAML files."""
    if not PLAN_DIR.exists():
        return set()

    urns = set()
    urn_pattern = re.compile(r"\\burn:\\s*(acc:[^\\s]+)")

    for plan_path in PLAN_DIR.rglob("*.yaml"):
        try:
            content = plan_path.read_text()
        except OSError:
            continue
        for match in urn_pattern.findall(content):
            urns.add(match.strip())

    return urns


def collect_contract_ids():
    """Return a mapping of contract $id to file path."""
    ids = {}
    for contract_path in find_all_contract_schemas():
        try:
            with open(contract_path) as f:
                contract = json.load(f)
        except json.JSONDecodeError:
            continue
        contract_id = contract.get("$id")
        if contract_id:
            ids[contract_id] = contract_path
    return ids


def iter_external_refs(schema):
    """Yield non-local $ref values from a JSON schema object."""
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "$ref" and isinstance(value, str) and not value.startswith("#"):
                yield value
            else:
                yield from iter_external_refs(value)
    elif isinstance(schema, list):
        for item in schema:
            yield from iter_external_refs(item)


@pytest.mark.platform
def test_contract_schemas_validate_against_meta_schema(meta_schema):
    """
    SPEC-PLATFORM-CONTRACTS-0010: All contract schemas validate against meta-schema

    Given: Contract schemas in contracts/
    When: Validating against .claude/schemas/tester/contract.schema.json
    Then: All contracts pass meta-schema validation
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    validation_errors = []
    missing_metadata = []

    for contract_path in contract_files:
        try:
            with open(contract_path) as f:
                contract = json.load(f)

            if "x-artifact-metadata" not in contract:
                missing_metadata.append(contract_path)
                continue

            # Validate against meta-schema
            validate(instance=contract, schema=meta_schema)

        except ValidationError as e:
            validation_errors.append(
                f"{contract_path.relative_to(REPO_ROOT)}: {e.message}"
            )
        except json.JSONDecodeError as e:
            validation_errors.append(
                f"{contract_path.relative_to(REPO_ROOT)}: Invalid JSON - {e}"
            )

    if missing_metadata:
        print(
            "Skipping meta-schema validation for contracts missing x-artifact-metadata:\n" +
            "\n".join(f"  {p.relative_to(REPO_ROOT)}" for p in missing_metadata[:10]) +
            (f"\n  ... and {len(missing_metadata) - 10} more" if len(missing_metadata) > 10 else "")
        )

    if validation_errors:
        pytest.fail(
            f"Found {len(validation_errors)} contract validation errors:\n" +
            "\n".join(f"  {err}" for err in validation_errors[:10]) +
            (f"\n  ... and {len(validation_errors) - 10} more" if len(validation_errors) > 10 else "")
        )


@pytest.mark.platform
def test_contract_versions_follow_semver():
    """
    SPEC-PLATFORM-CONTRACTS-0018: Contract versions follow semantic versioning

    Given: Contract schema version fields
    When: Checking version format
    Then: Versions match pattern: MAJOR.MINOR.PATCH
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    version_pattern = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
    invalid_versions = []

    for contract_path in contract_files:
        try:
            with open(contract_path) as f:
                contract = json.load(f)
        except json.JSONDecodeError:
            continue

        version = contract.get("version")
        if not version or not version_pattern.match(version):
            invalid_versions.append(
                f"{contract_path.relative_to(REPO_ROOT)}: version '{version}'"
            )

    if invalid_versions:
        pytest.fail(
            f"Found {len(invalid_versions)} contracts with invalid versions:\n" +
            "\n".join(f"  {err}" for err in invalid_versions[:10]) +
            (f"\n  ... and {len(invalid_versions) - 10} more" if len(invalid_versions) > 10 else "")
        )


@pytest.mark.platform
def test_contract_references_are_valid():
    """
    SPEC-PLATFORM-CONTRACTS-0019: Contract references point to existing contracts

    Given: Contract schemas with $ref or dependencies fields
    When: Resolving references
    Then: All referenced contracts exist
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    contract_ids = collect_contract_ids()
    contract_urns = {f"contract:{cid}" for cid in contract_ids.keys()}

    broken_refs = []

    for contract_path in contract_files:
        try:
            with open(contract_path) as f:
                contract = json.load(f)
        except json.JSONDecodeError:
            continue

        metadata = contract.get("x-artifact-metadata", {})
        dependencies = metadata.get("dependencies", []) if isinstance(metadata, dict) else []

        for dep in dependencies:
            if dep not in contract_urns:
                broken_refs.append(
                    f"{contract_path.relative_to(REPO_ROOT)}: dependency '{dep}' not found"
                )

        for ref in iter_external_refs(contract):
            if ref.startswith(("http://", "https://")):
                continue

            ref_path = ref.split("#", 1)[0]

            if ref_path.endswith(".schema.json"):
                resolved = (contract_path.parent / ref_path).resolve()
                if not resolved.exists():
                    broken_refs.append(
                        f"{contract_path.relative_to(REPO_ROOT)}: $ref '{ref}' not found"
                    )
                continue

            if ref.startswith("contract:"):
                if ref not in contract_urns:
                    broken_refs.append(
                        f"{contract_path.relative_to(REPO_ROOT)}: $ref '{ref}' not found"
                    )
                continue

            if ref_path not in contract_ids:
                broken_refs.append(
                    f"{contract_path.relative_to(REPO_ROOT)}: $ref '{ref}' not found"
                )

    if broken_refs:
        pytest.fail(
            f"Found {len(broken_refs)} contract references that cannot be resolved:\n" +
            "\n".join(f"  {err}" for err in broken_refs[:10]) +
            (f"\n  ... and {len(broken_refs) - 10} more" if len(broken_refs) > 10 else "")
        )


@pytest.mark.platform
def test_contract_acceptance_references_exist():
    """
    SPEC-PLATFORM-CONTRACTS-0020: Contract acceptance_refs point to existing criteria

    Given: Contract schemas with acceptance_refs array
    When: Checking acceptance criteria files
    Then: All referenced acceptance URNs exist in plan/ directories
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    acceptance_urns = load_plan_acceptance_urns()
    if not acceptance_urns:
        pytest.skip("No acceptance URNs found in plan/")

    urn_pattern = re.compile(
        r"^acc:[a-z][a-z0-9_-]*:([DLPCEMYRK][0-9]{3}-(UNIT|HTTP|EVENT|WS|E2E|A11Y|VIS|METRIC|JOB|DB|SEC|LOAD|SCRIPT|WIDGET|GOLDEN|BLOC|INTEGRATION|RLS|EDGE|REALTIME|STORAGE)-[0-9]{3}(?:-[a-z0-9-]+)?|[A-Z][0-9]{3})$"
    )

    missing = []

    for contract_path in contract_files:
        try:
            with open(contract_path) as f:
                contract = json.load(f)
        except json.JSONDecodeError:
            continue

        metadata = contract.get("x-artifact-metadata", {})
        traceability = metadata.get("traceability", {}) if isinstance(metadata, dict) else {}
        acceptance_refs = traceability.get("acceptance_refs", []) if isinstance(traceability, dict) else []

        for ref in acceptance_refs:
            if not urn_pattern.match(ref):
                missing.append(
                    f"{contract_path.relative_to(REPO_ROOT)}: acceptance_ref '{ref}' has invalid format"
                )
                continue
            if ref not in acceptance_urns:
                missing.append(
                    f"{contract_path.relative_to(REPO_ROOT)}: acceptance_ref '{ref}' not found in plan/"
                )

    if missing:
        pytest.fail(
            f"Found {len(missing)} invalid acceptance references:\n" +
            "\n".join(f"  {err}" for err in missing[:10]) +
            (f"\n  ... and {len(missing) - 10} more" if len(missing) > 10 else "")
        )


@pytest.mark.platform
def test_no_duplicate_contract_ids():
    """
    SPEC-PLATFORM-CONTRACTS-0021: Contract $id fields are unique

    Given: All contract schemas in contracts/
    When: Collecting $id values
    Then: No two schemas have the same $id
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    seen = {}
    duplicates = {}

    for contract_path in contract_files:
        try:
            with open(contract_path) as f:
                contract = json.load(f)
        except json.JSONDecodeError:
            continue

        contract_id = contract.get("$id")
        if not contract_id:
            continue
        if contract_id in seen:
            duplicates.setdefault(contract_id, [seen[contract_id]]).append(contract_path)
        else:
            seen[contract_id] = contract_path

    if duplicates:
        lines = []
        for contract_id, paths in duplicates.items():
            lines.append(f"$id: \"{contract_id}\"")
            for path in paths:
                lines.append(f"  - {path.relative_to(REPO_ROOT)}")

        pytest.fail(
            "Found duplicate contract IDs:\n" +
            "\n".join(lines)
        )


@pytest.mark.platform
def test_contract_id_format_follows_convention():
    """
    SPEC-PLATFORM-CONTRACTS-0011: Contract $id follows hierarchical pattern

    Given: Contract schemas
    When: Checking $id field format
    Then: $id matches pattern: {domain}:{resource}[.{category}]
          Uses colons for domain:resource hierarchy
          Uses dots for resource.category facets
          NO "contract:" prefix in $id (prefix only in wagon URNs)
          Version must be in separate 'version' field (NOT in $id)

    Examples:
      ✓ "$id": "match:result" with "version": "1.0.0"
      ✓ "$id": "match:episode.started" with "version": "1.0.0"
      ✓ "$id": "mechanic:decision.choice" with "version": "1.0.0"
      ✓ "$id": "commons:auth.claims" with "version": "1.0.0"
      ✗ "$id": "contract:match:result" (wrong - has "contract:" prefix)
      ✗ "$id": "match:result:v1" (wrong - version in $id)
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    # Pattern: {theme}(:{path})*:{resource}[.{category}][.{subcategory}]...
    # Allows multiple colons for hierarchical path (theme:domain:subdomain:resource)
    # Allows dots for category facets
    # NO "contract:" prefix, NO version in $id
    id_pattern = re.compile(r"^[a-z][a-z0-9\-]+(:[a-z][a-z0-9\-]+)+(\.[a-z][a-z0-9\-]+)*$")

    invalid_ids = []
    missing_version_field = []

    for contract_path in contract_files:
        try:
            with open(contract_path) as f:
                contract = json.load(f)

            contract_id = contract.get("$id")
            version_field = contract.get("version")

            if not contract_id:
                invalid_ids.append(
                    f"{contract_path.relative_to(REPO_ROOT)}: Missing $id field"
                )
            elif not id_pattern.match(contract_id):
                # Check if version is incorrectly included in $id
                if ":v" in contract_id or re.search(r":v?\d+(\.\d+)*$", contract_id):
                    invalid_ids.append(
                        f"{contract_path.relative_to(REPO_ROOT)}: "
                        f"$id '{contract_id}' includes version. Move version to separate 'version' field"
                    )
                else:
                    invalid_ids.append(
                        f"{contract_path.relative_to(REPO_ROOT)}: "
                        f"$id '{contract_id}' doesn't match pattern '{id_pattern.pattern}'"
                    )

            # Check for separate version field (recommended)
            if not version_field:
                missing_version_field.append(
                    f"{contract_path.relative_to(REPO_ROOT)}: Missing 'version' field (recommended)"
                )

        except json.JSONDecodeError:
            # Skip invalid JSON files (caught by other test)
            continue

    errors = []

    if invalid_ids:
        errors.append(
            f"Found {len(invalid_ids)} contracts with invalid $id format:\n" +
            "\n".join(f"  {err}" for err in invalid_ids[:10]) +
            (f"\n  ... and {len(invalid_ids) - 10} more" if len(invalid_ids) > 10 else "")
        )

    if missing_version_field:
        errors.append(
            f"\nFound {len(missing_version_field)} contracts missing 'version' field:\n" +
            "\n".join(f"  {err}" for err in missing_version_field[:10]) +
            (f"\n  ... and {len(missing_version_field) - 10} more" if len(missing_version_field) > 10 else "")
        )

    if errors:
        pytest.fail(
            "\n".join(errors) +
            f"\n\nExpected format:\n" +
            f"  $id: {{domain}}:{{resource}}[.{{category}}]  (NO 'contract:' prefix, NO version)\n" +
            f"  version: \"1.0.0\"  (separate field)\n" +
            f"\nExamples:\n" +
            f"  $id: match:result\n" +
            f"  $id: match:episode.started  (dot for category facet)\n" +
            f"  $id: mechanic:decision.choice  (dot for category facet)\n" +
            f"\nDo NOT use 'contract:' prefix or version in $id field"
        )


@pytest.mark.platform
def test_contract_directory_structure_matches_artifact():
    """
    SPEC-PLATFORM-CONTRACTS-0012: Directory structure mirrors $id hierarchy

    Given: Contract schemas
    When: Checking physical path vs $id field
    Then: File path mirrors $id with colons replaced by slashes
          Pattern: contracts/{$id with : → /}.schema.json
          Dots in $id represent facets (stay as dots in filename)

    Examples:
      - $id "match:dilemma:current" → contracts/match/dilemma/current.schema.json
      - $id "mechanic:timebank:exhausted" → contracts/mechanic/timebank/exhausted.schema.json
      - $id "commons:ux:foundations:color" → contracts/commons/ux/foundations/color.schema.json
      - $id "match:dilemma.paired" → contracts/match/dilemma.paired.schema.json (dot preserved)
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    structure_violations = []

    for contract_path in contract_files:
        try:
            with open(contract_path) as f:
                contract = json.load(f)

            contract_id = contract.get("$id")
            if not contract_id:
                continue

            # Convert $id to expected path: replace colons with slashes
            # Example: "mechanic:timebank:exhausted" → "mechanic/timebank/exhausted"
            # Dots stay as dots (facets): "match:dilemma.paired" → "match/dilemma.paired"
            id_parts = contract_id.split(":")
            expected_path_str = "/".join(id_parts) + ".schema.json"
            expected_path = Path(expected_path_str)

            # Get actual relative path
            actual_path = contract_path.relative_to(CONTRACTS_DIR)

            # Compare paths
            if actual_path != expected_path:
                structure_violations.append(
                    f"{contract_path.relative_to(REPO_ROOT)}: "
                    f"$id '{contract_id}' expects path contracts/{expected_path}, "
                    f"but found at contracts/{actual_path}"
                )

        except (json.JSONDecodeError, ValueError):
            continue

    if structure_violations:
        pytest.fail(
            f"Found {len(structure_violations)} directory structure violations:\n" +
            "\n".join(f"  {err}" for err in structure_violations[:10]) +
            (f"\n  ... and {len(structure_violations) - 10} more" if len(structure_violations) > 10 else "") +
            "\n\nRule: File path must mirror $id structure\n" +
            "  Pattern: contracts/{{$id with : replaced by /}}.schema.json\n" +
            "  Example: $id 'mechanic:timebank:exhausted' → contracts/mechanic/timebank/exhausted.schema.json"
        )


@pytest.mark.platform
def test_contract_api_method_inference():
    """
    SPEC-PLATFORM-CONTRACTS-0014: API method correctly inferred from resource

    Given: Contract schemas
    When: Checking API method in x-artifact-metadata
    Then: Method follows interface.convention.yaml api_mapping rules
          POST: choice, new, created, started, exhausted
          GET: result, active, config, foundations, identity, current, pool, paired
          PUT: updated, closed, completed
          DELETE: terminated, deleted
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    # Inference rules from interface.convention.yaml
    method_hints = {
        "POST": ["choice", "new", "created", "registered", "started", "exhausted"],
        "GET": ["result", "active", "config", "foundations", "identity", "current", "pool", "paired"],
        "PUT": ["updated", "closed", "completed"],
        "DELETE": ["terminated", "deleted"],
    }

    inference_errors = []

    for contract_path in contract_files:
        try:
            with open(contract_path) as f:
                contract = json.load(f)

            metadata = contract.get("x-artifact-metadata", {})
            resource = metadata.get("resource", "")
            api = metadata.get("api", {})
            method = api.get("method", "")

            if not resource or not method:
                continue

            # Extract base resource (before dot or colon)
            base_resource = resource.split(".")[0].split(":")[0]

            # Check if method matches inference rules
            expected_method = None
            for http_method, keywords in method_hints.items():
                if any(keyword in base_resource for keyword in keywords):
                    expected_method = http_method
                    break

            if expected_method and method != expected_method:
                inference_errors.append(
                    f"{contract_path.relative_to(REPO_ROOT)}: "
                    f"Resource '{resource}' suggests {expected_method}, "
                    f"but API method is {method}"
                )

        except (json.JSONDecodeError, KeyError):
            continue

    if inference_errors:
        pytest.fail(
            f"Found {len(inference_errors)} API method inference issues:\n" +
            "\n".join(f"  {err}" for err in inference_errors[:10]) +
            (f"\n  ... and {len(inference_errors) - 10} more" if len(inference_errors) > 10 else "")
        )


@pytest.mark.platform
def test_contract_traceability_richness():
    """
    SPEC-PLATFORM-CONTRACTS-0015: Contract metadata includes traceability fields

    Given: Contract schemas
    When: Checking x-artifact-metadata for traceability
    Then: Contracts include recommended fields for rich traceability:
          - testing.directory (path to atdd/)
          - testing.schema_tests (list of test files)
          - dependencies (array of contract URNs this depends on)
          - traceability.wagon_ref (path to wagon YAML)
          - traceability.feature_refs (array of feature URNs)

    This test generates a traceability report showing completion metrics.
    """
    contract_files = find_all_contract_schemas()

    if not contract_files:
        pytest.skip("No contract schema files found")

    traceability_report = {
        "testing_directory": 0,
        "testing_schema_tests": 0,
        "dependencies": 0,
        "traceability_wagon_ref": 0,
        "traceability_feature_refs": 0,
        "total_contracts": len(contract_files),
    }

    missing_traceability = []

    for contract_path in contract_files:
        try:
            with open(contract_path) as f:
                contract = json.load(f)

            metadata = contract.get("x-artifact-metadata", {})
            testing = metadata.get("testing", {})
            traceability = metadata.get("traceability", {})

            contract_name = f"{metadata.get('domain')}:{metadata.get('resource')}"
            missing_fields = []

            # Check testing fields
            if testing.get("directory"):
                traceability_report["testing_directory"] += 1
            else:
                missing_fields.append("testing.directory")

            if testing.get("schema_tests"):
                traceability_report["testing_schema_tests"] += 1
            else:
                missing_fields.append("testing.schema_tests")

            # Check dependencies
            if metadata.get("dependencies"):
                traceability_report["dependencies"] += 1
            else:
                missing_fields.append("dependencies")

            # Check traceability fields
            if traceability.get("wagon_ref"):
                traceability_report["traceability_wagon_ref"] += 1
            else:
                missing_fields.append("traceability.wagon_ref")

            if traceability.get("feature_refs"):
                traceability_report["traceability_feature_refs"] += 1
            else:
                missing_fields.append("traceability.feature_refs")

            if missing_fields:
                missing_traceability.append(
                    f"{contract_path.relative_to(REPO_ROOT)} ({contract_name}): "
                    f"missing {', '.join(missing_fields)}"
                )

        except (json.JSONDecodeError, KeyError):
            continue

    # Calculate percentages
    total = traceability_report["total_contracts"]
    report_lines = [
        "\n=== Contract Traceability Report ===",
        f"Total contracts analyzed: {total}",
        "",
        "Field coverage:",
        f"  testing.directory:         {traceability_report['testing_directory']}/{total} ({traceability_report['testing_directory']*100//total if total else 0}%)",
        f"  testing.schema_tests:      {traceability_report['testing_schema_tests']}/{total} ({traceability_report['testing_schema_tests']*100//total if total else 0}%)",
        f"  dependencies:              {traceability_report['dependencies']}/{total} ({traceability_report['dependencies']*100//total if total else 0}%)",
        f"  traceability.wagon_ref:    {traceability_report['traceability_wagon_ref']}/{total} ({traceability_report['traceability_wagon_ref']*100//total if total else 0}%)",
        f"  traceability.feature_refs: {traceability_report['traceability_feature_refs']}/{total} ({traceability_report['traceability_feature_refs']*100//total if total else 0}%)",
        "",
    ]

    # Calculate overall traceability score
    fields_checked = 5
    total_possible = total * fields_checked
    total_present = sum([
        traceability_report['testing_directory'],
        traceability_report['testing_schema_tests'],
        traceability_report['dependencies'],
        traceability_report['traceability_wagon_ref'],
        traceability_report['traceability_feature_refs'],
    ])
    overall_score = (total_present * 100 // total_possible) if total_possible else 0

    report_lines.append(f"Overall traceability score: {overall_score}% ({total_present}/{total_possible} fields)")

    if missing_traceability:
        report_lines.extend([
            "",
            f"Contracts missing traceability fields ({len(missing_traceability)}):",
        ])
        report_lines.extend(f"  {item}" for item in missing_traceability[:15])
        if len(missing_traceability) > 15:
            report_lines.append(f"  ... and {len(missing_traceability) - 15} more")

    # Print report (always, even if passing)
    print("\n".join(report_lines))

    # Test passes with warning if score < 80%
    if overall_score < 80:
        pytest.skip(
            f"Traceability score {overall_score}% is below 80% threshold. "
            "Consider enriching contract metadata for better governance."
        )
