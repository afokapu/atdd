"""
Shared fixtures for platform tests.

Provides schemas, file discovery, and validation utilities for E2E platform tests.
"""
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Tuple
import pytest


# Path constants
# File is at atdd/coach/audits/shared_fixtures.py, so go up 3 levels to reach repo root
REPO_ROOT = Path(__file__).resolve().parents[4]
PLAN_DIR = REPO_ROOT / "plan"
ATDD_DIR = REPO_ROOT / "atdd"
CONTRACTS_DIR = REPO_ROOT / "contracts"
TELEMETRY_DIR = REPO_ROOT / "telemetry"
WEB_DIR = REPO_ROOT / "web"


# Schema fixtures - Planner schemas
@pytest.fixture(scope="module")
def wagon_schema() -> Dict[str, Any]:
    """Load wagon.schema.json for validation."""
    with open(ATDD_DIR / "planner/schemas/wagon.schema.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def wmbt_schema() -> Dict[str, Any]:
    """Load wmbt.schema.json for validation."""
    with open(ATDD_DIR / "planner/schemas/wmbt.schema.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def feature_schema() -> Dict[str, Any]:
    """Load feature.schema.json for validation."""
    with open(ATDD_DIR / "planner/schemas/feature.schema.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def acceptance_schema() -> Dict[str, Any]:
    """Load acceptance.schema.json for validation."""
    with open(ATDD_DIR / "planner/schemas/acceptance.schema.json") as f:
        return json.load(f)


# Schema fixtures - Tester schemas
@pytest.fixture(scope="module")
def telemetry_signal_schema() -> Dict[str, Any]:
    """Load telemetry_signal.schema.json for validation."""
    schema_path = ATDD_DIR / "tester/schemas/telemetry_signal.schema.json"
    if schema_path.exists():
        with open(schema_path) as f:
            return json.load(f)
    return {}


@pytest.fixture(scope="module")
def telemetry_tracking_manifest_schema() -> Dict[str, Any]:
    """Load telemetry_tracking_manifest.schema.json for validation."""
    schema_path = ATDD_DIR / "tester/schemas/telemetry_tracking_manifest.schema.json"
    if schema_path.exists():
        with open(schema_path) as f:
            return json.load(f)
    return {}


# Generic schema loader
@pytest.fixture(scope="module")
def load_schema():
    """Factory fixture to load any schema by path."""
    def _loader(agent: str, schema_name: str) -> Dict[str, Any]:
        """
        Load a schema from atdd/{agent}/schemas/{schema_name}.

        Args:
            agent: Agent name (planner, tester, coach, coder)
            schema_name: Schema filename (e.g., "wagon.schema.json")

        Returns:
            Parsed JSON schema
        """
        schema_path = ATDD_DIR / agent / "schemas" / schema_name
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


# HTML Report Customization
def pytest_html_report_title(report):
    """Customize HTML report title."""
    report.title = "Platform Validation Test Report"


def pytest_configure(config):
    """Add custom metadata to HTML report."""
    config._metadata = {
        "Project": "Wagons Platform",
        "Test Suite": "Platform Validation",
        "Environment": "Development",
        "Python": "3.11",
        "Pytest": "8.4.2",
    }


def pytest_html_results_table_header(cells):
    """Customize HTML report table headers."""
    cells.insert(2, '<th>Category</th>')
    cells.insert(1, '<th class="sortable time" data-column-type="time">Duration</th>')


def pytest_html_results_table_row(report, cells):
    """Customize HTML report table rows."""
    # Add category based on test module
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
