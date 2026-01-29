"""
Test train infrastructure validation (SESSION-12).

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

Rationale:
Trains are production orchestration, not test infrastructure (SESSION-12).
These audits ensure the train composition root pattern is correctly implemented.
"""

import pytest
import ast
import re
from pathlib import Path
from typing import List, Dict, Set, Tuple


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
TRAINS_DIR = REPO_ROOT / "python" / "trains"
WAGONS_DIR = REPO_ROOT / "python"
GAME_PY = REPO_ROOT / "python" / "game.py"
E2E_CONFTEST = REPO_ROOT / "e2e" / "conftest.py"
CONTRACT_VALIDATOR = REPO_ROOT / "e2e" / "shared" / "fixtures" / "contract_validator.py"
TRAIN_CONVENTION = REPO_ROOT / "atdd" / "coder" / "conventions" / "train.convention.yaml"


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
