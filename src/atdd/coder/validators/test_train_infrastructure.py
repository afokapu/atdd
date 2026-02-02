"""
Test train infrastructure validation (SESSION-12 + Train First-Class Spec v0.6).

Validates conventions from:
- atdd/coder/conventions/train.convention.yaml
- atdd/coder/conventions/boundaries.convention.yaml
- atdd/coder/conventions/refactor.convention.yaml

Enforces:
- Train infrastructure exists (python/trains/)
- Wagons implement run_train() for train mode
- Contract validator is real (not mock)
- E2E tests use production TrainRunner
- Station Master pattern in game.py

Train First-Class Spec v0.6 additions:
- SPEC-TRAIN-VAL-0031: Backend runner paths
- SPEC-TRAIN-VAL-0032: Frontend code allowed roots
- SPEC-TRAIN-VAL-0033: FastAPI template enforcement

Rationale:
Trains are production orchestration, not test infrastructure (SESSION-12).
These audits ensure the train composition root pattern is correctly implemented.
"""

import pytest
import ast
import re
import yaml
from pathlib import Path
from typing import List, Dict, Set, Tuple, Any

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.train_spec_phase import (
    TrainSpecPhase,
    should_enforce,
    emit_phase_warning
)
from atdd.coach.utils.config import get_train_config


# Path constants
# Consumer repo artifacts
REPO_ROOT = find_repo_root()
TRAINS_DIR = REPO_ROOT / "python" / "trains"
WAGONS_DIR = REPO_ROOT / "python"
GAME_PY = REPO_ROOT / "python" / "game.py"
E2E_CONFTEST = REPO_ROOT / "e2e" / "conftest.py"
CONTRACT_VALIDATOR = REPO_ROOT / "e2e" / "shared" / "fixtures" / "contract_validator.py"

# Package resources (conventions, schemas)
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
TRAIN_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "train.convention.yaml"


def find_wagons() -> List[Path]:
    """Find all wagon.py files."""
    wagons = []
    for wagon_file in WAGONS_DIR.glob("*/wagon.py"):
        # Skip trains directory
        if "trains" in wagon_file.parts:
            continue
        wagons.append(wagon_file)
    return wagons


def has_run_train_function(file_path: Path) -> Tuple[bool, str]:
    """
    Check if wagon.py has run_train() function.

    Returns:
        (has_function, implementation_type)
        implementation_type: "function", "method", or "none"
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    try:
        tree = ast.parse(content)

        # Check for module-level function
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run_train":
                # Check if it's at module level (not inside a class)
                if isinstance(node, ast.FunctionDef):
                    return (True, "function")

        # Check for class method
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "run_train":
                        return (True, "method")

        return (False, "none")

    except SyntaxError:
        return (False, "none")


def extract_imports_from_file(file_path: Path) -> Set[str]:
    """Extract all import statements from a file."""
    imports = set()
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # Match: from X import Y or import X
            if 'import' in line and not line.strip().startswith('#'):
                imports.add(line.strip())
    return imports


# ============================================================================
# TRAIN INFRASTRUCTURE TESTS
# ============================================================================

def test_trains_directory_exists():
    """Train infrastructure must exist at python/trains/."""
    assert TRAINS_DIR.exists(), (
        f"Train infrastructure directory not found: {TRAINS_DIR}\n"
        "Expected: python/trains/\n"
        "See: atdd/coder/conventions/train.convention.yaml"
    )

    assert TRAINS_DIR.is_dir(), f"{TRAINS_DIR} exists but is not a directory"


def test_train_infrastructure_files_exist():
    """
    Train infrastructure files must exist.

    Required files:
    - python/trains/__init__.py
    - python/trains/runner.py (TrainRunner class)
    - python/trains/models.py (TrainSpec, TrainResult, Cargo)
    """
    required_files = {
        "__init__.py": "Package initialization",
        "runner.py": "TrainRunner class",
        "models.py": "Data models (TrainSpec, TrainResult, Cargo)"
    }

    missing_files = []
    for filename, description in required_files.items():
        file_path = TRAINS_DIR / filename
        if not file_path.exists():
            missing_files.append((filename, description))

    if missing_files:
        pytest.fail(
            f"\nMissing {len(missing_files)} train infrastructure files:\n\n" +
            "\n".join(f"  python/trains/{name}\n    Purpose: {desc}"
                     for name, desc in missing_files) +
            "\n\nSee: atdd/coder/conventions/train.convention.yaml::train_structure"
        )


def test_train_runner_class_exists():
    """TrainRunner class must exist in python/trains/runner.py."""
    runner_file = TRAINS_DIR / "runner.py"

    assert runner_file.exists(), f"runner.py not found: {runner_file}"

    with open(runner_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check for TrainRunner class
    assert "class TrainRunner" in content, (
        "TrainRunner class not found in python/trains/runner.py\n"
        "Expected: class TrainRunner with execute() method"
    )

    # Check for key methods
    required_methods = ["__init__", "execute", "_execute_step"]
    missing_methods = [m for m in required_methods if f"def {m}" not in content]

    if missing_methods:
        pytest.fail(
            f"\nTrainRunner missing required methods: {', '.join(missing_methods)}\n"
            "Expected methods: __init__, execute, _execute_step"
        )


def test_train_models_exist():
    """Train data models must exist in python/trains/models.py."""
    models_file = TRAINS_DIR / "models.py"

    assert models_file.exists(), f"models.py not found: {models_file}"

    with open(models_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check for required models
    required_models = ["TrainSpec", "TrainStep", "TrainResult", "Cargo"]
    missing_models = [m for m in required_models if f"class {m}" not in content]

    if missing_models:
        pytest.fail(
            f"\nMissing train models: {', '.join(missing_models)}\n"
            "Expected in python/trains/models.py:\n"
            "  - TrainSpec: Parsed train definition\n"
            "  - TrainStep: Single step in sequence\n"
            "  - TrainResult: Execution result\n"
            "  - Cargo: Artifacts passed between wagons"
        )


# ============================================================================
# WAGON TRAIN MODE TESTS
# ============================================================================

def test_wagons_implement_run_train():
    """
    Wagons must implement run_train() to participate in train orchestration.

    Expected signature:
    def run_train(inputs: Dict[str, Any], timing: Dict[str, float] = None) -> Dict[str, Any]

    Can be either:
    - Module-level function: def run_train(...)
    - Class method: class XxxWagon: def run_train(self, ...)
    """
    wagons = find_wagons()

    assert len(wagons) > 0, "No wagons found in python/ directory"

    missing_run_train = []
    for wagon_file in wagons:
        has_function, impl_type = has_run_train_function(wagon_file)
        if not has_function:
            wagon_name = wagon_file.parent.name
            missing_run_train.append(wagon_name)

    # Allow some wagons to not have run_train yet (partial migration)
    # But key wagons from SESSION-12 must have it
    required_wagons = ["pace_dilemmas", "supply_fragments", "juggle_domains", "resolve_dilemmas"]
    missing_required = [w for w in required_wagons if w in missing_run_train]

    if missing_required:
        pytest.fail(
            f"\nCritical wagons missing run_train() implementation:\n\n" +
            "\n".join(f"  python/{name}/wagon.py" for name in missing_required) +
            "\n\nExpected signature:\n"
            "  def run_train(inputs: Dict[str, Any], timing: Dict[str, float] = None) -> Dict[str, Any]\n"
            "\nSee: atdd/coder/conventions/train.convention.yaml::wagon_train_interface"
        )


# ============================================================================
# STATION MASTER TESTS (game.py)
# ============================================================================

def test_game_py_imports_train_runner():
    """game.py must import TrainRunner (Station Master pattern)."""
    assert GAME_PY.exists(), f"game.py not found: {GAME_PY}"

    imports = extract_imports_from_file(GAME_PY)

    has_train_import = any("trains.runner import TrainRunner" in imp for imp in imports)

    assert has_train_import, (
        "game.py must import TrainRunner\n"
        "Expected: from trains.runner import TrainRunner\n"
        "See: atdd/coder/conventions/train.convention.yaml::station_master"
    )


def test_game_py_has_journey_map():
    """game.py must have JOURNEY_MAP routing actions to trains."""
    with open(GAME_PY, 'r', encoding='utf-8') as f:
        content = f.read()

    assert "JOURNEY_MAP" in content, (
        "game.py must define JOURNEY_MAP dictionary\n"
        "Expected: JOURNEY_MAP = {'action': 'train_id', ...}\n"
        "See: atdd/coder/conventions/train.convention.yaml::station_master"
    )


def test_game_py_has_train_execution_endpoint():
    """game.py must have /trains/execute endpoint."""
    with open(GAME_PY, 'r', encoding='utf-8') as f:
        content = f.read()

    has_endpoint = '"/trains/execute"' in content or "'/trains/execute'" in content

    assert has_endpoint, (
        "game.py must have /trains/execute endpoint\n"
        "Expected: @app.post('/trains/execute')\n"
        "See: atdd/coder/conventions/train.convention.yaml::station_master"
    )


# ============================================================================
# E2E TEST INFRASTRUCTURE TESTS
# ============================================================================

def test_e2e_conftest_uses_production_train_runner():
    """
    E2E conftest must use production TrainRunner, not mocks.

    This ensures tests validate production orchestration (zero drift).
    """
    assert E2E_CONFTEST.exists(), f"E2E conftest not found: {E2E_CONFTEST}"

    imports = extract_imports_from_file(E2E_CONFTEST)

    # Should import from trains.runner (production)
    has_production_import = any("trains.runner import TrainRunner" in imp for imp in imports)

    # Should NOT import mock
    has_mock_import = any("mock_train_runner" in imp for imp in imports)

    assert has_production_import, (
        "E2E conftest must import production TrainRunner\n"
        "Expected: from trains.runner import TrainRunner\n"
        "Found: Mock import still present\n"
        "See: atdd/coder/conventions/train.convention.yaml::testing_pattern"
    )

    assert not has_mock_import, (
        "E2E conftest should NOT use MockTrainRunner\n"
        "Remove: from e2e.shared.fixtures.mock_train_runner import MockTrainRunner\n"
        "Use production TrainRunner instead"
    )


def test_contract_validator_is_real():
    """
    Contract validator must be real JSON schema validator, not mock.

    Real validator uses jsonschema library for contract validation.
    """
    assert CONTRACT_VALIDATOR.exists(), f"Contract validator not found: {CONTRACT_VALIDATOR}"

    with open(CONTRACT_VALIDATOR, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check for real implementation
    has_jsonschema = "import jsonschema" in content or "from jsonschema import" in content
    has_validate_method = "def validate(" in content

    assert has_jsonschema, (
        "Contract validator must use jsonschema library\n"
        "Expected: import jsonschema\n"
        "File: e2e/shared/fixtures/contract_validator.py"
    )

    assert has_validate_method, (
        "Contract validator must have validate() method\n"
        "Expected: def validate(self, artifact, schema_path)\n"
        "File: e2e/shared/fixtures/contract_validator.py"
    )

    # Check it's not a mock
    is_mock = "Mock" in content and "mock" in content.lower()

    assert not is_mock, (
        "Contract validator appears to be a mock\n"
        "Replace with real JSON schema validation\n"
        "See: atdd/coder/conventions/train.convention.yaml::cargo_pattern"
    )


def test_e2e_conftest_uses_real_contract_validator():
    """E2E conftest must use real ContractValidator, not mock."""
    imports = extract_imports_from_file(E2E_CONFTEST)

    # Should import real validator
    has_real_import = any("contract_validator import ContractValidator" in imp
                          and "mock" not in imp.lower()
                          for imp in imports)

    # Should NOT import mock
    has_mock_import = any("mock_contract_validator" in imp for imp in imports)

    assert has_real_import, (
        "E2E conftest must import real ContractValidator\n"
        "Expected: from e2e.shared.fixtures.contract_validator import ContractValidator\n"
        "File: e2e/conftest.py"
    )

    assert not has_mock_import, (
        "E2E conftest should NOT use MockContractValidator\n"
        "Remove: from e2e.shared.fixtures.mock_contract_validator import MockContractValidator\n"
        "Use real ContractValidator instead"
    )


# ============================================================================
# CONVENTION DOCUMENTATION TESTS
# ============================================================================

def test_train_convention_exists():
    """Train convention file must exist."""
    assert TRAIN_CONVENTION.exists(), (
        f"Train convention not found: {TRAIN_CONVENTION}\n"
        "Expected: atdd/coder/conventions/train.convention.yaml"
    )


def test_train_convention_documents_key_patterns():
    """
    Train convention must document key implementation patterns.

    Required sections:
    - composition_hierarchy (with train level)
    - wagon_train_mode (run_train signature)
    - cargo_pattern (artifact flow)
    - station_master (game.py pattern)
    - testing_pattern (E2E tests)
    """
    with open(TRAIN_CONVENTION, 'r', encoding='utf-8') as f:
        content = f.read()

    required_sections = [
        "composition_hierarchy",
        "wagon_train_mode",
        "cargo_pattern",
        "station_master",
        "testing_pattern"
    ]

    missing_sections = [s for s in required_sections if s not in content]

    if missing_sections:
        pytest.fail(
            f"\nTrain convention missing required sections:\n\n" +
            "\n".join(f"  - {section}" for section in missing_sections) +
            f"\n\nFile: {TRAIN_CONVENTION}\n"
            "See: SESSION-12 implementation plan for required documentation"
        )


# ============================================================================
# BOUNDARY ENFORCEMENT TESTS
# ============================================================================

def test_no_wagon_to_wagon_imports():
    """
    Wagons must NOT import from other wagons.

    Enforces boundary pattern: wagons communicate via contracts only.
    This is checked in wagon.py files specifically (not all python files).
    """
    wagons = find_wagons()
    violations = []

    for wagon_file in wagons:
        wagon_name = wagon_file.parent.name

        with open(wagon_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find imports from other wagons
        for other_wagon in wagons:
            other_name = other_wagon.parent.name
            if other_name == wagon_name:
                continue

            # Check for imports like: from other_wagon.xxx import
            pattern = f"from {other_name}\\."
            if re.search(pattern, content):
                violations.append((wagon_name, other_name, wagon_file))

    if violations:
        pytest.fail(
            f"\nFound {len(violations)} wagon boundary violations:\n\n" +
            "\n".join(f"  {wagon} imports from {other}\n    File: {file}"
                     for wagon, other, file in violations) +
            "\n\nWagons must communicate via contracts only, not direct imports\n"
            "See: atdd/coder/conventions/boundaries.convention.yaml"
        )


# ============================================================================
# TRAIN FIRST-CLASS SPEC v0.6 VALIDATORS
# ============================================================================


def _get_all_train_ids() -> List[str]:
    """Get all train IDs from registry."""
    train_ids = []
    trains_file = REPO_ROOT / "plan" / "_trains.yaml"

    if trains_file.exists():
        with open(trains_file) as f:
            data = yaml.safe_load(f)

        for theme_key, categories in data.get("trains", {}).items():
            if isinstance(categories, dict):
                for category_key, trains_list in categories.items():
                    if isinstance(trains_list, list):
                        for train in trains_list:
                            train_id = train.get("train_id")
                            if train_id:
                                train_ids.append(train_id)

    return train_ids


def test_backend_runner_paths():
    """
    SPEC-TRAIN-VAL-0031: Backend runner paths validation.

    Given: Train infrastructure
    When: Checking runner file locations
    Then: Runners exist at python/trains/runner.py or python/trains/<train_id>/runner.py

    Section 9: Backend Runner Paths
    """
    train_config = get_train_config(REPO_ROOT)
    allowed_paths = train_config.get("backend_runner_paths", [
        "python/trains/runner.py",
        "python/trains/{train_id}/runner.py"
    ])

    # Check for main runner
    main_runner = TRAINS_DIR / "runner.py"
    if not main_runner.exists():
        if should_enforce(TrainSpecPhase.BACKEND_ENFORCEMENT):
            pytest.fail(
                f"Main TrainRunner not found at {main_runner}\n"
                "Expected: python/trains/runner.py"
            )
        else:
            emit_phase_warning(
                "SPEC-TRAIN-VAL-0031",
                f"Main TrainRunner not found at {main_runner}",
                TrainSpecPhase.BACKEND_ENFORCEMENT
            )
        return

    # Check for train-specific runners if trains have custom runners
    train_ids = _get_all_train_ids()
    custom_runners = []

    for train_id in train_ids:
        custom_runner = TRAINS_DIR / train_id / "runner.py"
        if custom_runner.exists():
            custom_runners.append((train_id, custom_runner))

    # Validate custom runners extend base TrainRunner
    for train_id, runner_path in custom_runners:
        with open(runner_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if "TrainRunner" not in content:
            if should_enforce(TrainSpecPhase.BACKEND_ENFORCEMENT):
                pytest.fail(
                    f"Custom runner at {runner_path} does not reference TrainRunner\n"
                    "Custom runners should extend or use the base TrainRunner"
                )
            else:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0031",
                    f"Custom runner {train_id}/runner.py should reference TrainRunner",
                    TrainSpecPhase.BACKEND_ENFORCEMENT
                )


def test_frontend_code_allowed_roots():
    """
    SPEC-TRAIN-VAL-0032: Frontend code in allowed root directories.

    Given: Frontend (web) code files
    When: Checking file locations
    Then: Code is in allowed roots (web/src/, web/components/, web/pages/)

    Section 10: Frontend Code Allowed Roots
    """
    train_config = get_train_config(REPO_ROOT)
    allowed_roots = train_config.get("frontend_allowed_roots", [
        "web/src/",
        "web/components/",
        "web/pages/"
    ])

    web_dir = REPO_ROOT / "web"
    if not web_dir.exists():
        pytest.skip("No web/ directory found")

    # Find all TypeScript/JavaScript files in web/
    code_files = []
    for pattern in ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"]:
        code_files.extend(web_dir.glob(pattern))

    # Exclude test files, node_modules, and build directories
    code_files = [
        f for f in code_files
        if "node_modules" not in str(f)
        and ".next" not in str(f)
        and "dist" not in str(f)
        and not f.name.endswith(".test.ts")
        and not f.name.endswith(".test.tsx")
        and not f.name.endswith(".spec.ts")
    ]

    violations = []
    for code_file in code_files:
        rel_path = code_file.relative_to(REPO_ROOT)
        in_allowed_root = any(str(rel_path).startswith(root) for root in allowed_roots)

        # Also allow e2e/ directory for tests (already excluded above but be explicit)
        in_e2e = str(rel_path).startswith("web/e2e/")

        if not in_allowed_root and not in_e2e:
            # Check if it's a config file at root level (allow those)
            is_config = code_file.parent == web_dir and code_file.suffix in [".js", ".ts"]
            if not is_config:
                violations.append(str(rel_path))

    if violations and len(violations) > 10:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Frontend code outside allowed roots ({len(violations)} files):\n  " +
                "\n  ".join(violations[:10]) +
                f"\n  ... and {len(violations) - 10} more" +
                f"\n\nAllowed roots: {allowed_roots}"
            )
        else:
            emit_phase_warning(
                "SPEC-TRAIN-VAL-0032",
                f"{len(violations)} frontend files outside allowed roots",
                TrainSpecPhase.FULL_ENFORCEMENT
            )


def test_fastapi_template_enforcement():
    """
    SPEC-TRAIN-VAL-0033: FastAPI template enforcement when configured.

    Given: .atdd/config.yaml with enforce_fastapi_template=true
    When: Checking API endpoint files
    Then: Endpoints follow FastAPI template conventions

    Section 11: FastAPI Template Enforcement
    """
    train_config = get_train_config(REPO_ROOT)

    if not train_config.get("enforce_fastapi_template", False):
        pytest.skip("FastAPI template enforcement not enabled in config")

    # Look for FastAPI app files
    python_dir = REPO_ROOT / "python"
    if not python_dir.exists():
        pytest.skip("No python/ directory found")

    # Find files that define FastAPI apps
    fastapi_files = []
    for py_file in python_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()

            if "FastAPI" in content and ("app = FastAPI" in content or "router = APIRouter" in content):
                fastapi_files.append(py_file)
        except Exception:
            pass

    if not fastapi_files:
        pytest.skip("No FastAPI app files found")

    # Check template conventions
    violations = []
    for api_file in fastapi_files:
        with open(api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for required template elements
        required_elements = [
            ("response_model", "Endpoints should use response_model parameter"),
            ("HTTPException", "Endpoints should use HTTPException for errors"),
        ]

        for element, description in required_elements:
            if element not in content:
                violations.append(f"{api_file.name}: {description}")

    if violations:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"FastAPI template violations:\n  " + "\n  ".join(violations) +
                "\n\nSee: train.convention.yaml for FastAPI template requirements"
            )
        else:
            for violation in violations:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0033",
                    violation,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )
