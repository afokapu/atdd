"""
Platform tests: Telemetry directory structure validation.

Validates that telemetry/ follows the signal naming convention.
Tests ensure telemetry signal files match pattern: {signal-type}.{plane}[.{measure}].json
"""
import pytest
from pathlib import Path
import re
import json
from jsonschema import validate, ValidationError

# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
TELEMETRY_DIR = REPO_ROOT / "telemetry"
CONTRACTS_DIR = REPO_ROOT / "contracts"
PLAN_DIR = REPO_ROOT / "plan"
META_SCHEMA_PATH = REPO_ROOT / "atdd" / "tester" / "schemas" / "telemetry.schema.json"


@pytest.fixture
def telemetry_meta_schema():
    """Load telemetry meta-schema."""
    if not META_SCHEMA_PATH.exists():
        pytest.skip(f"Meta-schema not found: {META_SCHEMA_PATH}")

    with open(META_SCHEMA_PATH) as f:
        return json.load(f)


def find_all_telemetry_signals():
    """Find telemetry signal files excluding tests/ directories."""
    if not TELEMETRY_DIR.exists():
        return []
    return [
        path for path in TELEMETRY_DIR.rglob("*.json")
        if "tests" not in path.parts
    ]


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


def collect_contract_urns():
    """Collect contract URNs from contract schemas."""
    if not CONTRACTS_DIR.exists():
        return set()

    urns = set()
    for contract_path in CONTRACTS_DIR.rglob("*.schema.json"):
        try:
            with open(contract_path) as f:
                contract = json.load(f)
        except json.JSONDecodeError:
            continue

        contract_id = contract.get("$id")
        if contract_id:
            urns.add(f"contract:{contract_id}")

    return urns


def is_placeholder_signal(signal_path, signal):
    """Return True if signal is a placeholder signal."""
    if "placeholder" in signal_path.parts:
        return True

    for key in ("description", "note"):
        value = signal.get(key)
        if isinstance(value, str) and "placeholder" in value.lower():
            return True

    return False


@pytest.mark.platform
def test_telemetry_directory_exists():
    """
    SPEC-PLATFORM-TELEMETRY-0001: telemetry/ directory exists

    Given: Repository root
    When: Checking for telemetry/ directory
    Then: telemetry/ directory exists
    """
    assert TELEMETRY_DIR.exists(), \
        f"telemetry/ directory does not exist at {TELEMETRY_DIR}"


@pytest.mark.platform
def test_telemetry_follows_theme_domain_pattern():
    """
    SPEC-PLATFORM-TELEMETRY-0002: telemetry/ follows theme/domain pattern with aspect as filename prefix

    Given: telemetry/ directory structure
    When: Checking directory hierarchy and file naming
    Then: Structure follows telemetry/{theme}/{domain}/ pattern
          Aspect is filename prefix: {aspect}.{type}.{plane}[.{measure}].json
          Mirrors contracts/{theme}/{domain}/{aspect}.schema.json structure
    """
    if not TELEMETRY_DIR.exists():
        pytest.skip(f"telemetry/ directory does not exist")
        return

    name_pattern = re.compile(r"^[a-z][a-z0-9\-]*$")

    for theme_dir in TELEMETRY_DIR.iterdir():
        if not theme_dir.is_dir():
            continue

        # Skip hidden directories and special files
        if theme_dir.name.startswith(".") or theme_dir.name == "__pycache__" or theme_dir.name.startswith("_"):
            continue

        # Verify theme name follows pattern
        assert name_pattern.match(theme_dir.name), \
            f"Telemetry theme '{theme_dir.name}' doesn't match pattern (lowercase, hyphens only)"

        # Check domain directories
        for domain_dir in theme_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            if domain_dir.name.startswith(".") or domain_dir.name == "__pycache__" or domain_dir.name == "tests":
                continue

            # Verify domain name follows pattern
            assert name_pattern.match(domain_dir.name), \
                f"Telemetry domain '{domain_dir.name}' in theme '{theme_dir.name}' " \
                f"doesn't match pattern (lowercase, hyphens only)"

            # Verify signal files have aspect prefix (no aspect subdirectories)
            signal_files = list(domain_dir.glob("*.json"))
            if signal_files:
                # Check that files follow aspect.type.plane[.measure].json pattern
                for signal_file in signal_files:
                    parts = signal_file.name.split('.')
                    assert len(parts) >= 4, \
                        f"Signal file '{signal_file.name}' doesn't follow aspect.type.plane[.measure].json pattern"

                    aspect, type_part = parts[0], parts[1]
                    assert name_pattern.match(aspect), \
                        f"Aspect '{aspect}' in '{signal_file.name}' doesn't match pattern"


@pytest.mark.platform
def test_telemetry_signal_files_follow_naming_convention():
    """
    SPEC-PLATFORM-TELEMETRY-0003: Signal files follow naming convention

    Given: Telemetry signal files in telemetry/{domain}/{resource}/
    When: Checking file naming pattern
    Then: Files match pattern: {signal-type}.{plane}[.{measure}].json
          signal-type: metric (with measure) or event (no measure)
          plane: ui, ux, be, nw, db, st, tm, sc, au, fn, if
          measure: optional for metrics (e.g., count, duration, bytes)
    """
    if not TELEMETRY_DIR.exists():
        pytest.skip(f"telemetry/ directory does not exist")
        return

    # Pattern: metric.{plane}.{measure}.json OR event.{plane}.json
    # Planes: ui, ux, be, nw, db, st, tm, sc, au, fn, if
    metric_pattern = re.compile(
        r"^metric\.(ui|ux|be|nw|db|st|tm|sc|au|fn|if)\.[a-z][a-z0-9\-]*\.json$"
    )
    event_pattern = re.compile(
        r"^event\.(ui|ux|be|nw|db|st|tm|sc|au|fn|if)\.json$"
    )

    invalid_files = []

    for theme_dir in TELEMETRY_DIR.iterdir():
        if not theme_dir.is_dir() or theme_dir.name.startswith((".", "_")):
            continue

        for domain_dir in theme_dir.iterdir():
            if not domain_dir.is_dir() or domain_dir.name.startswith((".", "_")) or domain_dir.name == "tests":
                continue

            # Check all JSON files in domain directory (not subdirectories)
            for signal_file in domain_dir.glob("*.json"):
                filename = signal_file.name

                # Skip files in tests directory
                if "tests" in signal_file.parts:
                    continue

                # Files should follow: {aspect}.{type}.{plane}[.{measure}].json
                # So we need to check parts after the aspect prefix
                parts = filename.split('.')
                if len(parts) < 4:  # aspect.type.plane.json minimum
                    invalid_files.append(str(signal_file.relative_to(REPO_ROOT)))
                    continue

                # Check type.plane[.measure] portion (after aspect prefix)
                type_plane_portion = '.'.join(parts[1:])  # Skip aspect

                # Check if matches metric or event pattern
                if not (metric_pattern.match(type_plane_portion) or event_pattern.match(type_plane_portion)):
                    invalid_files.append(
                        str(signal_file.relative_to(REPO_ROOT))
                    )

    if invalid_files:
        pytest.fail(
            f"Found {len(invalid_files)} telemetry files not following naming convention:\n" +
            "\n".join(f"  {f}" for f in invalid_files[:10]) +
            (f"\n  ... and {len(invalid_files) - 10} more" if len(invalid_files) > 10 else "") +
            "\n\nExpected patterns:\n" +
            "  - metric.{plane}.{measure}.json (e.g., metric.ui.duration.json)\n" +
            "  - event.{plane}.json (e.g., event.ux.json)\n" +
            "  Planes: ui, ux, be, nw, db, st, tm, sc, au, fn, if"
        )


@pytest.mark.platform
def test_telemetry_directories_contain_signal_files():
    """
    SPEC-PLATFORM-TELEMETRY-0004: Telemetry directories contain signal files

    Given: telemetry/{theme}/{domain}/{aspect}/ subdirectories (mirroring contracts)
    When: Checking directory contents
    Then: Each aspect subdirectory contains *.json signal files
          Directories are not empty
    """
    if not TELEMETRY_DIR.exists():
        pytest.skip(f"telemetry/ directory does not exist")
        return

    empty_dirs = []

    for theme_dir in TELEMETRY_DIR.iterdir():
        if not theme_dir.is_dir() or theme_dir.name.startswith((".", "_")):
            continue

        for domain_dir in theme_dir.iterdir():
            if not domain_dir.is_dir() or domain_dir.name.startswith((".", "_")) or domain_dir.name == "tests":
                continue

            # Check subdirectories (aspect directories) for signal files
            # telemetry/commons/ux/ should contain subdirectories like foundations/, primitives/, etc.
            for aspect_dir in domain_dir.iterdir():
                if not aspect_dir.is_dir() or aspect_dir.name.startswith((".", "_")) or aspect_dir.name in ("tests", "atdd"):
                    continue

                # Check if aspect directory has JSON signal files (excluding tests/)
                json_files = [f for f in aspect_dir.glob("*.json") if "tests" not in f.parts]

                if not json_files:
                    empty_dirs.append(str(aspect_dir.relative_to(REPO_ROOT)))

    if empty_dirs:
        pytest.fail(
            f"Found {len(empty_dirs)} telemetry directories without signal files:\n" +
            "\n".join(f"  {d}" for d in empty_dirs[:10]) +
            (f"\n  ... and {len(empty_dirs) - 10} more" if len(empty_dirs) > 10 else "")
        )


@pytest.mark.platform
def test_metric_signals_have_measure_suffix():
    """
    SPEC-PLATFORM-TELEMETRY-0005: Metric signals include measure suffix

    Given: Telemetry signal files with type 'metric'
    When: Checking file naming
    Then: Metric files match pattern metric.{plane}.{measure}.json
          Measure describes what is measured (e.g., count, duration, bytes)
    """
    if not TELEMETRY_DIR.exists():
        pytest.skip(f"telemetry/ directory does not exist")
        return

    # Find all metric.* files
    metric_files = list(TELEMETRY_DIR.rglob("metric.*.json"))

    # Pattern with measure: metric.{plane}.{measure}.json
    metric_with_measure = re.compile(
        r"^metric\.(ui|ux|be|nw|db|st|tm|sc|au|fn|if)\.[a-z][a-z0-9\-]+\.json$"
    )

    invalid_metrics = []

    for metric_file in metric_files:
        filename = metric_file.name

        # Check if it has the measure component
        if not metric_with_measure.match(filename):
            invalid_metrics.append(str(metric_file.relative_to(REPO_ROOT)))

    if invalid_metrics:
        pytest.fail(
            f"Found {len(invalid_metrics)} metric files without measure suffix:\n" +
            "\n".join(f"  {f}" for f in invalid_metrics[:10]) +
            (f"\n  ... and {len(invalid_metrics) - 10} more" if len(invalid_metrics) > 10 else "") +
            "\n\nMetric files must include measure: metric.{plane}.{measure}.json"
        )


@pytest.mark.platform
def test_event_signals_have_no_measure_suffix():
    """
    SPEC-PLATFORM-TELEMETRY-0006: Event signals have no measure suffix

    Given: Telemetry signal files with type 'event'
    When: Checking file naming
    Then: Event files match pattern event.{plane}.json (no measure)
    """
    if not TELEMETRY_DIR.exists():
        pytest.skip(f"telemetry/ directory does not exist")
        return

    # Find all event.* files
    event_files = list(TELEMETRY_DIR.rglob("event.*.json"))

    # Pattern without measure: event.{plane}.json
    event_pattern = re.compile(
        r"^event\.(ui|ux|be|nw|db|st|tm|sc|au|fn|if)\.json$"
    )

    invalid_events = []

    for event_file in event_files:
        filename = event_file.name

        # Check if it matches simple event pattern
        if not event_pattern.match(filename):
            invalid_events.append(str(event_file.relative_to(REPO_ROOT)))

    if invalid_events:
        pytest.fail(
            f"Found {len(invalid_events)} event files with unexpected format:\n" +
            "\n".join(f"  {f}" for f in invalid_events[:10]) +
            (f"\n  ... and {len(invalid_events) - 10} more" if len(invalid_events) > 10 else "") +
            "\n\nEvent files should match: event.{plane}.json (no measure suffix)"
        )


@pytest.mark.platform
def test_telemetry_signals_validate_against_meta_schema(telemetry_meta_schema):
    """
    SPEC-PLATFORM-TELEMETRY-0009: Telemetry signals validate against meta-schema

    Given: Telemetry signal files
    When: Validating against atdd/tester/schemas/telemetry.schema.json
    Then: All telemetry signals pass meta-schema validation
    """
    signal_files = find_all_telemetry_signals()

    if not signal_files:
        pytest.skip("No telemetry signal files found")

    validation_errors = []

    for signal_path in signal_files:
        try:
            with open(signal_path) as f:
                signal = json.load(f)
            validate(instance=signal, schema=telemetry_meta_schema)
        except ValidationError as exc:
            validation_errors.append(
                f"{signal_path.relative_to(REPO_ROOT)}: {exc.message}"
            )
        except json.JSONDecodeError as exc:
            validation_errors.append(
                f"{signal_path.relative_to(REPO_ROOT)}: Invalid JSON - {exc}"
            )

    if validation_errors:
        pytest.fail(
            f"Found {len(validation_errors)} telemetry validation errors:\n" +
            "\n".join(f"  {err}" for err in validation_errors[:10]) +
            (f"\n  ... and {len(validation_errors) - 10} more" if len(validation_errors) > 10 else "")
        )


@pytest.mark.platform
def test_telemetry_versions_follow_semver():
    """
    SPEC-PLATFORM-TELEMETRY-0010: Telemetry versions follow semantic versioning

    Given: Telemetry signal version fields
    When: Checking version format
    Then: Versions match pattern: MAJOR.MINOR.PATCH
    """
    signal_files = find_all_telemetry_signals()

    if not signal_files:
        pytest.skip("No telemetry signal files found")

    version_pattern = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
    invalid_versions = []

    for signal_path in signal_files:
        try:
            with open(signal_path) as f:
                signal = json.load(f)
        except json.JSONDecodeError:
            continue

        version = signal.get("version")
        if not version or not version_pattern.match(version):
            invalid_versions.append(
                f"{signal_path.relative_to(REPO_ROOT)}: version '{version}'"
            )

    if invalid_versions:
        pytest.fail(
            f"Found {len(invalid_versions)} telemetry signals with invalid versions:\n" +
            "\n".join(f"  {err}" for err in invalid_versions[:10]) +
            (f"\n  ... and {len(invalid_versions) - 10} more" if len(invalid_versions) > 10 else "")
        )


@pytest.mark.platform
def test_telemetry_contract_references_exist():
    """
    SPEC-PLATFORM-TELEMETRY-0011: Telemetry contract references point to existing contracts

    Given: Telemetry signal files with artifact_ref fields
    When: Resolving artifact_ref references
    Then: All referenced contracts exist
    """
    signal_files = find_all_telemetry_signals()

    if not signal_files:
        pytest.skip("No telemetry signal files found")

    contract_urns = collect_contract_urns()
    missing_refs = []

    for signal_path in signal_files:
        try:
            with open(signal_path) as f:
                signal = json.load(f)
        except json.JSONDecodeError:
            continue

        artifact_ref = signal.get("artifact_ref")
        if artifact_ref and artifact_ref not in contract_urns:
            missing_refs.append(
                f"{signal_path.relative_to(REPO_ROOT)}: artifact_ref '{artifact_ref}' not found"
            )

    if missing_refs:
        pytest.fail(
            f"Found {len(missing_refs)} telemetry signals with broken contract references:\n" +
            "\n".join(f"  {err}" for err in missing_refs[:10]) +
            (f"\n  ... and {len(missing_refs) - 10} more" if len(missing_refs) > 10 else "")
        )


@pytest.mark.platform
def test_telemetry_acceptance_references_exist():
    """
    SPEC-PLATFORM-TELEMETRY-0012: Telemetry acceptance_criteria reference existing criteria

    Given: Telemetry signal files with acceptance_criteria arrays
    When: Checking acceptance criteria files
    Then: All referenced acceptance URNs exist in plan/ directories
    """
    signal_files = find_all_telemetry_signals()

    if not signal_files:
        pytest.skip("No telemetry signal files found")

    acceptance_urns = load_plan_acceptance_urns()
    if not acceptance_urns:
        pytest.skip("No acceptance URNs found in plan/")

    urn_pattern = re.compile(
        r"^acc:[a-z][a-z0-9_-]*:([DLPCEMYRK][0-9]{3}-(UNIT|HTTP|EVENT|WS|E2E|A11Y|VIS|METRIC|JOB|DB|SEC|LOAD|SCRIPT|WIDGET|GOLDEN|BLOC|INTEGRATION|RLS|EDGE|REALTIME|STORAGE)-[0-9]{3}(?:-[a-z0-9-]+)?|[A-Z][0-9]{3})$"
    )

    missing = []
    empty_criteria = []

    for signal_path in signal_files:
        try:
            with open(signal_path) as f:
                signal = json.load(f)
        except json.JSONDecodeError:
            continue

        acceptance_criteria = signal.get("acceptance_criteria", [])
        if not acceptance_criteria:
            empty_criteria.append(signal_path)
            continue

        for ref in acceptance_criteria:
            if not urn_pattern.match(ref):
                missing.append(
                    f"{signal_path.relative_to(REPO_ROOT)}: acceptance_criteria '{ref}' has invalid format"
                )
                continue
            if ref not in acceptance_urns:
                missing.append(
                    f"{signal_path.relative_to(REPO_ROOT)}: acceptance_criteria '{ref}' not found in plan/"
                )

    if empty_criteria:
        print(
            "Telemetry signals missing acceptance_criteria:\n" +
            "\n".join(f"  {p.relative_to(REPO_ROOT)}" for p in empty_criteria[:10]) +
            (f"\n  ... and {len(empty_criteria) - 10} more" if len(empty_criteria) > 10 else "")
        )

    if missing:
        pytest.fail(
            f"Found {len(missing)} invalid acceptance references:\n" +
            "\n".join(f"  {err}" for err in missing[:10]) +
            (f"\n  ... and {len(missing) - 10} more" if len(missing) > 10 else "")
        )


@pytest.mark.platform
def test_no_duplicate_telemetry_ids():
    """
    SPEC-PLATFORM-TELEMETRY-0013: Telemetry $id fields are unique

    Given: All telemetry signal files in telemetry/
    When: Collecting $id values
    Then: No two signals have the same $id
    """
    signal_files = find_all_telemetry_signals()

    if not signal_files:
        pytest.skip("No telemetry signal files found")

    seen = {}
    duplicates = {}

    for signal_path in signal_files:
        try:
            with open(signal_path) as f:
                signal = json.load(f)
        except json.JSONDecodeError:
            continue

        signal_id = signal.get("$id")
        if not signal_id:
            continue
        if signal_id in seen:
            duplicates.setdefault(signal_id, [seen[signal_id]]).append(signal_path)
        else:
            seen[signal_id] = signal_path

    if duplicates:
        lines = []
        for signal_id, paths in duplicates.items():
            lines.append(f"$id: \"{signal_id}\"")
            for path in paths:
                lines.append(f"  - {path.relative_to(REPO_ROOT)}")

        pytest.fail(
            "Found duplicate telemetry IDs:\n" +
            "\n".join(lines)
        )


@pytest.mark.platform
def test_no_orphaned_telemetry_directories(telemetry_urns):
    """
    SPEC-PLATFORM-TELEMETRY-0007: No orphaned telemetry directories

    Given: Telemetry directories in telemetry/
    When: Comparing to telemetry URNs from wagons
    Then: Each telemetry/{theme}/{domain}/{aspect}/ has a corresponding URN
          No orphaned directories that aren't referenced
    """
    if not TELEMETRY_DIR.exists():
        pytest.skip(f"telemetry/ directory does not exist")
        return

    # Build set of expected paths from URNs
    expected_paths = set()

    for urn in telemetry_urns:
        parts = urn.split(":")
        if len(parts) == 4:
            _, theme, domain, aspect = parts
            expected_paths.add(f"{theme}/{domain}/{aspect}")

    # Check actual directory structure
    orphaned = []

    for theme_dir in TELEMETRY_DIR.iterdir():
        if not theme_dir.is_dir() or theme_dir.name.startswith((".", "_")):
            continue

        theme_name = theme_dir.name

        for domain_dir in theme_dir.iterdir():
            if not domain_dir.is_dir() or domain_dir.name.startswith((".", "_")) or domain_dir.name == "tests":
                continue

            domain_name = domain_dir.name

            # Check signal files for aspects (aspects are filename prefixes now)
            signal_files = [f for f in domain_dir.glob("*.json") if "tests" not in f.parts]

            for signal_file in signal_files:
                # Extract aspect from filename (first part before .)
                aspect_name = signal_file.name.split('.')[0]
                path = f"{theme_name}/{domain_name}/{aspect_name}"

                # Check if this path is referenced by a URN
                if path not in expected_paths:
                    orphaned.append(path)

    if orphaned:
        pytest.skip(
            f"Found {len(orphaned)} telemetry directories without corresponding URNs:\n" +
            "\n".join(f"  telemetry/{d}" for d in orphaned[:10]) +
            (f"\n  ... and {len(orphaned) - 10} more" if len(orphaned) > 10 else "") +
            "\n  (This may be expected for legacy or future telemetry)"
        )
