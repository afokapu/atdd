"""
Shared fixtures for platform tests.

Provides schemas, file discovery, and validation utilities for E2E platform tests.

Path resolution strategy:
- REPO_ROOT (via find_repo_root()) = consumer repository artifacts (plan/, contracts/, etc.)
- ATDD_PKG_DIR (via atdd.__file__) = installed package resources (schemas, conventions)

Validators should use:
- REPO_ROOT for consumer repo artifacts (plan/, contracts/, telemetry/, web/, python/)
- ATDD_PKG_DIR for package-bundled resources (schemas, conventions, templates)
"""
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import pytest

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import load_atdd_config, get_train_config


# Path constants
# Consumer repo artifacts - use find_repo_root() to locate consumer repository
REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"
CONTRACTS_DIR = REPO_ROOT / "contracts"
TELEMETRY_DIR = REPO_ROOT / "telemetry"
WEB_DIR = REPO_ROOT / "web"

# Package resources - use atdd.__file__ to locate installed package
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent


# Schema fixtures - Planner schemas (loaded from installed package)
@pytest.fixture(scope="module")
def wagon_schema() -> Dict[str, Any]:
    """Load wagon.schema.json for validation."""
    with open(ATDD_PKG_DIR / "planner/schemas/wagon.schema.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def wmbt_schema() -> Dict[str, Any]:
    """Load wmbt.schema.json for validation."""
    with open(ATDD_PKG_DIR / "planner/schemas/wmbt.schema.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def feature_schema() -> Dict[str, Any]:
    """Load feature.schema.json for validation."""
    with open(ATDD_PKG_DIR / "planner/schemas/feature.schema.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def acceptance_schema() -> Dict[str, Any]:
    """Load acceptance.schema.json for validation."""
    with open(ATDD_PKG_DIR / "planner/schemas/acceptance.schema.json") as f:
        return json.load(f)


# Schema fixtures - Tester schemas (loaded from installed package)
@pytest.fixture(scope="module")
def telemetry_signal_schema() -> Dict[str, Any]:
    """Load telemetry_signal.schema.json for validation."""
    schema_path = ATDD_PKG_DIR / "tester/schemas/telemetry_signal.schema.json"
    if schema_path.exists():
        with open(schema_path) as f:
            return json.load(f)
    return {}


@pytest.fixture(scope="module")
def telemetry_tracking_manifest_schema() -> Dict[str, Any]:
    """Load telemetry_tracking_manifest.schema.json for validation."""
    schema_path = ATDD_PKG_DIR / "tester/schemas/telemetry_tracking_manifest.schema.json"
    if schema_path.exists():
        with open(schema_path) as f:
            return json.load(f)
    return {}


# Generic schema loader (loads from installed package)
@pytest.fixture(scope="module")
def load_schema():
    """Factory fixture to load any schema by path."""
    def _loader(agent: str, schema_name: str) -> Dict[str, Any]:
        """
        Load a schema from the installed atdd package.

        Args:
            agent: Agent name (planner, tester, coach, coder)
            schema_name: Schema filename (e.g., "wagon.schema.json")

        Returns:
            Parsed JSON schema
        """
        schema_path = ATDD_PKG_DIR / agent / "schemas" / schema_name
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema not found: {schema_path}")
        with open(schema_path) as f:
            return json.load(f)
    return _loader


# File discovery fixtures
@pytest.fixture(scope="module")
def wagon_manifests() -> List[Tuple[Path, Dict[str, Any]]]:
    """
    Discover all wagon manifests in plan/.

    Returns:
        List of (path, manifest_data) tuples
    """
    manifests = []

    # Load from _wagons.yaml registry
    wagons_file = PLAN_DIR / "_wagons.yaml"
    if wagons_file.exists():
        with open(wagons_file) as f:
            wagons_data = yaml.safe_load(f)
            for wagon_entry in wagons_data.get("wagons", []):
                if "manifest" in wagon_entry:
                    manifest_path = REPO_ROOT / wagon_entry["manifest"]
                    if manifest_path.exists():
                        with open(manifest_path) as mf:
                            manifest_data = yaml.safe_load(mf)
                            manifests.append((manifest_path, manifest_data))

    # Also discover individual wagon manifests (pattern: plan/*/_{wagon}.yaml)
    if not PLAN_DIR.exists():
        return manifests
    for wagon_dir in PLAN_DIR.iterdir():
        if wagon_dir.is_dir() and not wagon_dir.name.startswith("_"):
            for manifest_file in wagon_dir.glob("_*.yaml"):
                manifest_path = manifest_file
                if manifest_path not in [m[0] for m in manifests]:
                    with open(manifest_path) as f:
                        manifest_data = yaml.safe_load(f)
                        manifests.append((manifest_path, manifest_data))

    return manifests


@pytest.fixture(scope="module")
def trains_registry() -> Dict[str, Any]:
    """
    Load trains registry from plan/_trains.yaml.

    Returns:
        Trains data organized by theme (e.g., {"commons": [...], "scenario": [...]})
        or empty dict with all themes if file doesn't exist
    """
    trains_file = PLAN_DIR / "_trains.yaml"
    if trains_file.exists():
        with open(trains_file) as f:
            data = yaml.safe_load(f)
            trains_data = data.get("trains", {})

            # Flatten the nested structure
            # Input: {"0-commons": {"00-commons-nominal": [train1, train2], ...}, ...}
            # Output: {"commons": [train1, train2, ...], ...}
            flattened = {}
            for theme_key, categories in trains_data.items():
                # Extract theme name (e.g., "0-commons" -> "commons")
                theme = theme_key.split("-", 1)[1] if "-" in theme_key else theme_key
                flattened[theme] = []

                # Flatten all category lists into single theme list
                if isinstance(categories, dict):
                    for category_key, trains_list in categories.items():
                        if isinstance(trains_list, list):
                            flattened[theme].extend(trains_list)

            return flattened

    # Return empty theme-grouped structure
    return {
        "commons": [],
        "mechanic": [],
        "scenario": [],
        "match": [],
        "sensory": [],
        "player": [],
        "league": [],
        "audience": [],
        "monetization": [],
        "partnership": []
    }


@pytest.fixture(scope="module")
def trains_registry_with_groups() -> Dict[str, Dict[str, List[Dict]]]:
    """
    Load trains registry preserving full group structure for theme validation.

    Returns:
        Trains data with full nesting preserved:
        {"0-commons": {"00-commons-nominal": [train1, train2], ...}, ...}

    This fixture is used for validating theme derivation from group keys.
    """
    trains_file = PLAN_DIR / "_trains.yaml"
    if trains_file.exists():
        with open(trains_file) as f:
            data = yaml.safe_load(f)
            return data.get("trains", {})
    return {}


@pytest.fixture(scope="module")
def train_files() -> List[Tuple[Path, Dict]]:
    """
    Load all train YAML files with their data.

    Returns:
        List of (path, train_data) tuples for all train files in plan/_trains/
    """
    trains_dir = PLAN_DIR / "_trains"
    train_files_data = []

    if trains_dir.exists():
        for train_file in sorted(trains_dir.glob("*.yaml")):
            if not train_file.name.startswith("_"):
                try:
                    with open(train_file) as f:
                        train_data = yaml.safe_load(f)
                        if train_data:
                            train_files_data.append((train_file, train_data))
                except Exception:
                    pass

    return train_files_data


@pytest.fixture(scope="module")
def atdd_config() -> Dict[str, Any]:
    """
    Load .atdd/config.yaml configuration.

    Returns:
        Configuration dict with train and validation settings
    """
    return load_atdd_config(REPO_ROOT)


@pytest.fixture(scope="module")
def train_config() -> Dict[str, Any]:
    """
    Load train-specific configuration with defaults.

    Returns:
        Train configuration dict with defaults applied
    """
    return get_train_config(REPO_ROOT)


@pytest.fixture(scope="module")
def wagons_registry() -> Dict[str, Any]:
    """
    Load wagons registry from plan/_wagons.yaml.

    Returns:
        Wagons data or empty dict if file doesn't exist
    """
    wagons_file = PLAN_DIR / "_wagons.yaml"
    if wagons_file.exists():
        with open(wagons_file) as f:
            return yaml.safe_load(f)
    return {"wagons": []}


# URN resolution fixtures
@pytest.fixture(scope="module")
def contract_urns(wagon_manifests: List[Tuple[Path, Dict[str, Any]]]) -> List[str]:
    """
    Extract all contract URNs from wagon produce items.

    Returns:
        List of unique contract URNs (e.g., "contract:ux:foundations")
    """
    urns = set()
    for _, manifest in wagon_manifests:
        for produce_item in manifest.get("produce", []):
            contract = produce_item.get("contract")
            if contract and contract is not None:
                urns.add(contract)
    return sorted(urns)


@pytest.fixture(scope="module")
def telemetry_urns(wagon_manifests: List[Tuple[Path, Dict[str, Any]]]) -> List[str]:
    """
    Extract all telemetry URNs from wagon produce items.

    Returns:
        List of unique telemetry URNs (e.g., "telemetry:ux:foundations")
    """
    urns = set()
    for _, manifest in wagon_manifests:
        for produce_item in manifest.get("produce", []):
            telemetry = produce_item.get("telemetry")
            if telemetry and telemetry is not None:
                # Handle both string and list types
                if isinstance(telemetry, list):
                    urns.update(telemetry)
                else:
                    urns.add(telemetry)
    return sorted(urns)


@pytest.fixture(scope="module")
def typescript_test_files() -> List[Path]:
    """
    Discover all TypeScript test files in supabase/ and e2e/ directories.

    Returns:
        List of Path objects pointing to *.test.ts files
    """
    ts_tests = []

    # Search in supabase/functions/*/test/
    supabase_dir = REPO_ROOT / "supabase"
    if supabase_dir.exists():
        ts_tests.extend(supabase_dir.rglob("*.test.ts"))

    # Search in e2e/
    e2e_dir = REPO_ROOT / "e2e"
    if e2e_dir.exists():
        ts_tests.extend(e2e_dir.rglob("*.test.ts"))

    return sorted(ts_tests)


@pytest.fixture(scope="module")
def web_typescript_test_files() -> List[Path]:
    """
    Discover all Preact TypeScript test files in web/tests/.

    Returns:
        List of Path objects pointing to *.test.ts and *.test.tsx files
    """
    web_tests_dir = REPO_ROOT / "web" / "tests"
    if not web_tests_dir.exists():
        return []

    ts_tests = []
    ts_tests.extend(web_tests_dir.rglob("*.test.ts"))
    ts_tests.extend(web_tests_dir.rglob("*.test.tsx"))
    return sorted(ts_tests)


# Helper functions
def parse_urn(urn: str) -> Tuple[str, str, str]:
    """
    Parse URN into components.

    Args:
        urn: URN string like "contract:ux:foundations"

    Returns:
        Tuple of (type, domain, resource)

    Example:
        >>> parse_urn("contract:ux:foundations")
        ("contract", "ux", "foundations")
    """
    parts = urn.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid URN format: {urn} (expected type:domain:resource)")
    return tuple(parts)


def get_wagon_slug(manifest: Dict[str, Any]) -> str:
    """Extract wagon slug from manifest."""
    return manifest.get("wagon", "")


def get_produce_names(manifest: Dict[str, Any]) -> List[str]:
    """Extract produce artifact names from manifest."""
    return [item.get("name", "") for item in manifest.get("produce", [])]


def get_consume_names(manifest: Dict[str, Any]) -> List[str]:
    """Extract consume artifact names from manifest."""
    return [item.get("name", "") for item in manifest.get("consume", [])]


# HTML Report Customization (only when pytest-html is installed)
try:
    import pytest_html as _pytest_html_check  # noqa: F401
    _HAS_PYTEST_HTML = True
except ImportError:
    _HAS_PYTEST_HTML = False


def pytest_configure(config):
    """Add custom metadata to HTML report."""
    if hasattr(config, '_metadata'):
        config._metadata = {
            "Project": "Wagons Platform",
            "Test Suite": "Platform Validation",
            "Environment": "Development",
            "Python": "3.11",
            "Pytest": "8.4.2",
        }


if _HAS_PYTEST_HTML:
    def pytest_html_report_title(report):
        """Customize HTML report title."""
        report.title = "Platform Validation Test Report"

    def pytest_html_results_table_header(cells):
        """Customize HTML report table headers."""
        cells.insert(2, '<th>Category</th>')
        cells.insert(1, '<th class="sortable time" data-column-type="time">Duration</th>')

    def pytest_html_results_table_row(report, cells):
        """Customize HTML report table rows."""
        category = "Unknown"
        if hasattr(report, 'nodeid'):
            if 'wagons' in report.nodeid:
                category = '📋 Schema'
            elif 'cross_refs' in report.nodeid:
                category = '🔗 References'
            elif 'urn_resolution' in report.nodeid:
                category = '🗺️ URN Resolution'
            elif 'uniqueness' in report.nodeid:
                category = '🎯 Uniqueness'
            elif 'contracts_structure' in report.nodeid:
                category = '📄 Contracts'
            elif 'telemetry_structure' in report.nodeid:
                category = '📊 Telemetry'

        cells.insert(2, f'<td>{category}</td>')
        cells.insert(1, f'<td class="col-duration">{getattr(report, "duration", 0):.2f}s</td>')

    def pytest_html_results_summary(prefix, summary, postfix):
        """Add custom summary to HTML report."""
        prefix.extend([
            '<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); '
            'padding: 20px; border-radius: 8px; color: white; margin: 20px 0;">'
            '<h2 style="margin: 0 0 10px 0;">🚀 Platform Validation Suite</h2>'
            '<p style="margin: 0; opacity: 0.9;">E2E validation of repository data '
            'against platform schemas and conventions.</p>'
            '</div>'
        ])


# ============================================================================
# COVERAGE VALIDATION FIXTURES (ATDD Hierarchy Coverage Spec v0.1)
# ============================================================================


@pytest.fixture(scope="module")
def coverage_exceptions(atdd_config: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Load coverage exception allow-lists from .atdd/config.yaml.

    Returns:
        Dict mapping exception type to list of allowed URNs/slugs
    """
    return atdd_config.get("coverage", {}).get("exceptions", {})


@pytest.fixture(scope="module")
def coverage_thresholds(atdd_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load coverage threshold settings from .atdd/config.yaml.

    Returns:
        Dict with threshold settings (min_acceptance_coverage, etc.)
    """
    defaults = {"min_acceptance_coverage": 80}
    thresholds = atdd_config.get("coverage", {}).get("thresholds", {})
    return {**defaults, **thresholds}


@pytest.fixture(scope="module")
def feature_files() -> List[Tuple[Path, Dict[str, Any]]]:
    """
    Discover all feature files in plan/*/features/.

    Returns:
        List of (path, feature_data) tuples
    """
    import re
    features = []
    if not PLAN_DIR.exists():
        return features

    for wagon_dir in PLAN_DIR.iterdir():
        if wagon_dir.is_dir() and not wagon_dir.name.startswith("_"):
            features_dir = wagon_dir / "features"
            if features_dir.exists():
                for feature_file in features_dir.glob("*.yaml"):
                    try:
                        with open(feature_file) as f:
                            data = yaml.safe_load(f)
                            if data:
                                features.append((feature_file, data))
                    except Exception:
                        pass
    return features


@pytest.fixture(scope="module")
def wmbt_files() -> List[Tuple[Path, Dict[str, Any]]]:
    """
    Discover all WMBT files in plan/*/.

    WMBT files match pattern: [DLPCEMYRK]NNN.yaml (e.g., D001.yaml, L010.yaml)

    Returns:
        List of (path, wmbt_data) tuples
    """
    import re
    wmbts = []
    if not PLAN_DIR.exists():
        return wmbts

    wmbt_pattern = re.compile(r"^[DLPCEMYRK]\d{3}\.yaml$")

    for wagon_dir in PLAN_DIR.iterdir():
        if wagon_dir.is_dir() and not wagon_dir.name.startswith("_"):
            for wmbt_file in wagon_dir.glob("*.yaml"):
                if wmbt_pattern.match(wmbt_file.name):
                    try:
                        with open(wmbt_file) as f:
                            data = yaml.safe_load(f)
                            if data:
                                wmbts.append((wmbt_file, data))
                    except Exception:
                        pass
    return wmbts


@pytest.fixture(scope="module")
def acceptance_urns_by_wagon(wmbt_files: List[Tuple[Path, Dict[str, Any]]]) -> Dict[str, List[str]]:
    """
    Extract all acceptance URNs grouped by wagon slug.

    Returns:
        Dict mapping wagon slug to list of acceptance URNs
    """
    by_wagon: Dict[str, List[str]] = {}

    for path, wmbt_data in wmbt_files:
        # Derive wagon slug from directory name (snake_case -> kebab-case)
        wagon_slug = path.parent.name.replace("_", "-")

        if wagon_slug not in by_wagon:
            by_wagon[wagon_slug] = []

        for acc in wmbt_data.get("acceptances", []):
            if isinstance(acc, dict) and "identity" in acc:
                urn = acc["identity"].get("urn", "")
                if urn:
                    by_wagon[wagon_slug].append(urn)
            elif isinstance(acc, str):
                by_wagon[wagon_slug].append(acc)

    return by_wagon


@pytest.fixture(scope="module")
def all_acceptance_urns(acceptance_urns_by_wagon: Dict[str, List[str]]) -> List[str]:
    """
    Get flat list of all acceptance URNs across all wagons.

    Returns:
        List of all acceptance URNs
    """
    all_urns = []
    for urns in acceptance_urns_by_wagon.values():
        all_urns.extend(urns)
    return all_urns


@pytest.fixture(scope="module")
def wagon_to_train_mapping(train_files: List[Tuple[Path, Dict]]) -> Dict[str, List[str]]:
    """
    Build mapping of wagon slugs to train IDs that reference them.

    Returns:
        Dict mapping wagon slug to list of train IDs
    """
    mapping: Dict[str, List[str]] = {}

    for train_path, train_data in train_files:
        train_id = train_data.get("train_id", train_path.stem)
        participants = train_data.get("participants", [])

        for participant in participants:
            if isinstance(participant, str) and participant.startswith("wagon:"):
                wagon_slug = participant.replace("wagon:", "")
                if wagon_slug not in mapping:
                    mapping[wagon_slug] = []
                mapping[wagon_slug].append(train_id)

    return mapping


# ============================================================================
# LOCALIZATION FIXTURES (Localization Manifest Spec v1)
# ============================================================================


@pytest.fixture(scope="module")
def locale_manifest_path(atdd_config: Dict[str, Any]) -> Optional[Path]:
    """
    Get path to localization manifest file from config.

    Returns:
        Path to manifest file, or None if localization not configured
    """
    manifest_rel = atdd_config.get("localization", {}).get("manifest")
    if not manifest_rel:
        return None
    return REPO_ROOT / manifest_rel


@pytest.fixture(scope="module")
def locale_manifest(locale_manifest_path: Optional[Path]) -> Optional[Dict[str, Any]]:
    """
    Load localization manifest from configured path.

    Returns:
        Manifest dict with reference, locales, namespaces, or None if not configured
    """
    if locale_manifest_path is None:
        return None
    if not locale_manifest_path.exists():
        return None

    with open(locale_manifest_path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def locales_dir(locale_manifest_path: Optional[Path]) -> Optional[Path]:
    """
    Get locales directory (parent of manifest file).

    Returns:
        Path to locales directory, or None if not configured
    """
    if locale_manifest_path is None:
        return None
    return locale_manifest_path.parent
