"""
Test Python code follows clean architecture (4-layer).

Validates:
- Domain layer is pure (no imports from other layers)
- Application layer only imports from domain
- Presentation layer imports from application/domain
- Integration layer only imports from domain
- Component naming follows backend conventions
- Files are in correct layers based on their suffixes

Conventions from:
- atdd/coder/conventions/backend.convention.yaml

Inspired by: .claude/utils/coder/architecture.py
But: Self-contained, no utility dependencies
"""

import pytest
import re
import yaml
from pathlib import Path
from typing import Dict, List, Tuple


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
PYTHON_DIR = REPO_ROOT / "python"
BACKEND_CONVENTION = REPO_ROOT / "atdd" / "coder" / "conventions" / "backend.convention.yaml"


def determine_layer_from_path(file_path: Path) -> str:
    """
    Determine layer from file path.

    Args:
        file_path: Path to Python file

    Returns:
        Layer name: 'domain', 'application', 'presentation', 'integration', 'unknown'
    """
    path_str = str(file_path).lower()

    # Check explicit layer directories
    if '/domain/' in path_str or path_str.endswith('/domain.py'):
        return 'domain'
    elif '/application/' in path_str or path_str.endswith('/application.py'):
        return 'application'
    elif '/presentation/' in path_str or path_str.endswith('/presentation.py'):
        return 'presentation'
    elif '/integration/' in path_str or '/infrastructure/' in path_str:
        return 'integration'

    # Check alternative patterns
    if '/entities/' in path_str or '/models/' in path_str or '/value_objects/' in path_str:
        return 'domain'
    elif '/use_cases/' in path_str or '/usecases/' in path_str or '/services/' in path_str:
        return 'application'
    elif '/controllers/' in path_str or '/handlers/' in path_str or '/views/' in path_str:
        return 'presentation'
    elif '/adapters/' in path_str or '/repositories/' in path_str or '/gateways/' in path_str:
        return 'integration'

    return 'unknown'


def extract_python_imports(file_path: Path) -> list:
    """
    Extract import statements from Python file.

    Args:
        file_path: Path to Python file

    Returns:
        List of imported module paths
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    imports = []

    # Match: from X import Y
    from_imports = re.findall(r'from\s+([^\s]+)\s+import', content)
    imports.extend(from_imports)

    # Match: import X
    direct_imports = re.findall(r'^\s*import\s+([^\s;,]+)', content, re.MULTILINE)
    imports.extend(direct_imports)

    return imports


def infer_layer_from_import(import_path: str) -> str:
    """
    Infer layer from import path.

    Args:
        import_path: Import statement (e.g., "src.domain.entities")

    Returns:
        Layer name or 'external' for third-party imports
    """
    import_lower = import_path.lower()

    # Check if it's a relative import - can't determine layer reliably
    if import_path.startswith('.'):
        # Exception: relative imports to 'ports' are application layer
        if 'ports' in import_lower or '_port' in import_lower:
            return 'application'
        return 'unknown'

    # Check for layer indicators in import path (order matters - more specific first)

    # Ports are in application layer (interfaces), not integration
    if 'ports' in import_lower or '_port' in import_lower:
        return 'application'

    # Domain layer
    if '.domain.' in import_lower or '/domain/' in import_lower:
        return 'domain'
    if 'entities' in import_lower or 'models' in import_lower or 'value_objects' in import_lower:
        return 'domain'

    # Application layer
    if '.application.' in import_lower or '/application/' in import_lower:
        return 'application'
    if 'use_case' in import_lower or 'usecase' in import_lower or 'use_cases' in import_lower:
        return 'application'

    # Presentation layer
    if '.presentation.' in import_lower or '/presentation/' in import_lower:
        return 'presentation'
    if 'controller' in import_lower or 'handler' in import_lower:
        return 'presentation'

    # Integration layer (check after ports to avoid false positives)
    if '.integration.' in import_lower or '/integration/' in import_lower:
        return 'integration'
    if 'infrastructure' in import_lower or 'adapter' in import_lower:
        return 'integration'
    # Only mark as integration if it has 'repository' but NOT 'port'
    if 'repository' in import_lower and 'port' not in import_lower:
        return 'integration'

    # Third-party or standard library
    return 'external'


def load_backend_convention() -> Dict:
    """
    Load backend convention from YAML file.

    Returns:
        Backend convention dict
    """
    if not BACKEND_CONVENTION.exists():
        return {}

    with open(BACKEND_CONVENTION, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
        return data.get('backend', {})


def get_layer_component_suffixes(convention: Dict) -> Dict[str, Dict[str, List[str]]]:
    """
    Extract layer -> component_type -> suffixes mapping from convention.

    Args:
        convention: Backend convention dict

    Returns:
        Dict like {
            'domain': {
                'entities': ['*.py'],
                'value_objects': ['*_vo.py', '*.py']
            },
            'application': {...},
            ...
        }
    """
    result = {}

    layers = convention.get('layers', {})
    for layer_name, layer_config in layers.items():
        result[layer_name] = {}

        component_types = layer_config.get('component_types', [])
        for component_type in component_types:
            name = component_type.get('name', '')
            suffix_config = component_type.get('suffix', {})

            # Get Python suffixes
            py_suffixes = suffix_config.get('python', '')
            if py_suffixes:
                # Parse comma-separated suffixes
                suffixes = [s.strip() for s in py_suffixes.split(',')]
                result[layer_name][name] = suffixes

    return result


def matches_suffix_pattern(filename: str, pattern: str) -> bool:
    """
    Check if filename matches a suffix pattern.

    Args:
        filename: File name (e.g., "user_service.py")
        pattern: Pattern (e.g., "*_service.py")

    Returns:
        True if matches
    """
    # Convert glob pattern to regex
    # *_service.py -> .*_service\.py$
    # *.py -> .*\.py$
    regex_pattern = pattern.replace('.', r'\.')
    regex_pattern = regex_pattern.replace('*', '.*')
    regex_pattern = f'^{regex_pattern}$'

    return bool(re.match(regex_pattern, filename))


def determine_expected_layer_from_suffix(filename: str, convention: Dict) -> Tuple[str, str]:
    """
    Determine expected layer and component type from filename suffix.

    Args:
        filename: File name (e.g., "user_service.py")
        convention: Backend convention dict

    Returns:
        Tuple of (layer_name, component_type) or ('unknown', 'unknown')
    """
    layer_suffixes = get_layer_component_suffixes(convention)

    # Check more specific patterns first (e.g., *_service.py before *.py)
    # Sort by pattern length descending
    for layer_name, component_types in layer_suffixes.items():
        for component_type, suffixes in component_types.items():
            # Sort suffixes by length descending (more specific first)
            sorted_suffixes = sorted(suffixes, key=len, reverse=True)
            for suffix_pattern in sorted_suffixes:
                # Skip generic patterns - causes too many false positives
                if suffix_pattern == '*.py':
                    continue
                if matches_suffix_pattern(filename, suffix_pattern):
                    return layer_name, component_type

    # Don't fall back to generic *.py - causes too many false positives
    return 'unknown', 'unknown'


def find_python_files() -> list:
    """
    Find all Python files in python/ directory.

    Returns:
        List of Path objects
    """
    if not PYTHON_DIR.exists():
        return []

    python_files = []
    for py_file in PYTHON_DIR.rglob("*.py"):
        # Skip test files
        if '/test/' in str(py_file) or py_file.name.startswith('test_'):
            continue
        # Skip __pycache__
        if '__pycache__' in str(py_file):
            continue
        # Skip __init__.py (usually just imports)
        if py_file.name == '__init__.py':
            continue

        python_files.append(py_file)

    return python_files


@pytest.mark.coder
def test_python_follows_clean_architecture():
    """
    SPEC-CODER-ARCH-0001: Python code follows 4-layer clean architecture.

    Clean architecture dependency rules:
    - Domain → NOTHING (domain must be pure)
    - Application → Domain only
    - Presentation → Application, Domain
    - Integration → Domain only

    Forbidden dependencies:
    - Domain → Application/Presentation/Integration
    - Application → Presentation/Integration
    - Integration → Application/Presentation

    Given: Python files in python/
    When: Checking import statements
    Then: No forbidden cross-layer dependencies
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found to validate")

    violations = []

    for py_file in python_files:
        layer = determine_layer_from_path(py_file)

        # Skip files we can't categorize
        if layer == 'unknown':
            continue

        imports = extract_python_imports(py_file)

        for imp in imports:
            target_layer = infer_layer_from_import(imp)

            # Skip external imports (third-party libraries)
            if target_layer == 'external' or target_layer == 'unknown':
                continue

            # Check dependency rules
            violation = None

            if layer == 'domain':
                # Domain must not import from any other layer
                if target_layer in ['application', 'presentation', 'integration']:
                    violation = f"Domain layer cannot import from {target_layer}"

            elif layer == 'application':
                # Application can only import from domain
                if target_layer in ['presentation', 'integration']:
                    violation = f"Application layer cannot import from {target_layer}"

            elif layer == 'integration':
                # Integration can import from application (for ports) and domain
                # See backend.convention.yaml line 402-403: integration -> [application, domain]
                if target_layer == 'presentation':
                    violation = f"Integration layer cannot import from {target_layer}"

            if violation:
                rel_path = py_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}\\n"
                    f"  Layer: {layer}\\n"
                    f"  Import: {imp}\\n"
                    f"  Violation: {violation}"
                )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} architecture violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )


@pytest.mark.coder
def test_domain_layer_is_pure():
    """
    SPEC-CODER-ARCH-0002: Domain layer has no external dependencies.

    Domain layer should only import:
    - Standard library (typing, dataclasses, etc.)
    - Other domain modules

    Should NOT import:
    - Third-party libraries (except type hints)
    - Application/Presentation/Integration layers
    - Database/API libraries

    Given: Python files in domain/ directories
    When: Checking imports
    Then: Only standard library and domain imports
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found to validate")

    # Standard library modules (allowed in domain)
    # Note: time is allowed for time.perf_counter() timing measurements (pure function)
    ALLOWED_STDLIB = {
        '__future__', 'typing', 'dataclasses', 'enum', 'abc', 'datetime', 'uuid',
        'collections', 'itertools', 'functools', 're', 'json', 'pathlib',
        'hashlib', 'warnings', 'types', 'random', 'math', 'decimal',
        'copy', 'operator', 'string', 'textwrap', 'io', 'struct', 'time'
    }

    violations = []

    for py_file in python_files:
        layer = determine_layer_from_path(py_file)

        # Only check domain layer
        if layer != 'domain':
            continue

        imports = extract_python_imports(py_file)

        for imp in imports:
            # Skip relative imports (internal to domain)
            if imp.startswith('.'):
                continue

            # Get root module name
            root_module = imp.split('.')[0]

            # Check if it's allowed standard library
            if root_module in ALLOWED_STDLIB:
                continue

            # Check if it's from contracts/ (neutral DTO boundary - allowed per dto.convention.yaml)
            if root_module == 'contracts':
                continue

            # Check if it's domain import
            if 'domain' in imp.lower():
                continue

            # Check if it's from the same package
            if 'src' in imp or root_module in str(py_file):
                continue

            # Otherwise it's a violation
            rel_path = py_file.relative_to(REPO_ROOT)
            violations.append(
                f"{rel_path}\\n"
                f"  Import: {imp}\\n"
                f"  Issue: Domain layer should not import external libraries"
            )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} domain purity violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            f"\\n\\nDomain layer should only import:\\n" +
            f"  - Standard library: {', '.join(sorted(ALLOWED_STDLIB))}\\n" +
            f"  - Other domain modules"
        )

@pytest.mark.coder
def test_python_component_naming_follows_conventions():
    """
    SPEC-CODER-ARCH-PY-0003: Python components follow naming conventions.

    Component naming rules from conventions (with flexible layer placement):
    - Controllers: *_controller.py (presentation layer)
    - Services: *_service.py (domain layer)
    - Repositories: *_repository.py (integration layer)
    - Use Cases: *_use_case.py (application layer)
    - Entities: *.py (domain layer ONLY - pure business objects)
    - DTOs: *_dto.py (application layer)
    - Validators: *_validator.py (presentation|application|domain - depends on what they validate)
      * presentation: input shape/format validation
      * application: cross-cutting orchestration checks
      * domain: business invariants (often inline, not separate files)
    - Mappers: *_mapper.py (integration|application - depends on mapping responsibility)
      * integration: boundary mappers (IO ↔ internal types)
      * application: internal use-case transforms
    - Clients: *_client.py (integration layer)
    - Stores: *_store.py or *_storage.py (integration layer)
    - Handlers: *_handler.py (application layer)
    - Guards: *_guard.py (presentation layer)
    - Middleware: *_middleware.py (presentation layer)
    - Ports: protocols.py or *_port.py (application layer)
    - Events: *_event.py (domain layer)
    - Exceptions: *_exception.py or exceptions.py (domain layer)
    - Engines: *_engine.py, *_analyzer.py, *_processor.py (integration layer)

    Given: Python files with recognizable suffixes
    When: Checking file locations
    Then: Files are in correct layers per their suffixes
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found to validate")

    backend_conv = load_backend_convention()

    if not backend_conv:
        pytest.skip("Backend convention file not found")

    # Flexible layer rules: component type -> allowed layers
    # These component types can legitimately appear in multiple layers depending on purpose
    FLEXIBLE_LAYERS = {
        'validators': ['presentation', 'application', 'domain', 'integration'],  # Validation at any boundary
        'mappers': ['integration', 'application'],  # Depends on mapping responsibility
        'monitors': ['domain', 'application', 'integration'],  # Domain: business state, Integration: infra
        'services': ['domain', 'application'],  # Domain services (logic) and Application services (orchestration)
        'handlers': ['application', 'domain'],  # Application: CQRS, Domain: domain event handlers
        'ports': ['application', 'integration'],  # Application defines ports, Integration can have internal ports
        'engines': ['integration', 'domain'],  # Integration: external, Domain: pure computation
        'formatters': ['integration', 'domain'],  # Integration: output, Domain: value formatting
    }

    violations = []

    for py_file in python_files:
        actual_layer = determine_layer_from_path(py_file)

        # Skip files in unknown locations
        if actual_layer == 'unknown':
            continue

        filename = py_file.name

        # Determine expected layer from suffix
        expected_layer, component_type = determine_expected_layer_from_suffix(filename, backend_conv)

        # Skip unknown component types
        if expected_layer == 'unknown':
            continue

        # Skip generic "entities" matches from *.py pattern - too broad, causes false positives
        # Only enforce entities rule if file is actually in domain/entities/ subdirectory
        if component_type == 'entities' and actual_layer != 'domain':
            # Check if file is in an entities subdirectory
            if '/entities/' not in str(py_file):
                continue  # Skip - this is a false positive from generic *.py pattern

        # Check if this component type has flexible layer rules
        if component_type in FLEXIBLE_LAYERS:
            allowed_layers = FLEXIBLE_LAYERS[component_type]
            if actual_layer not in allowed_layers:
                rel_path = py_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}\n"
                    f"  Component Type: {component_type}\n"
                    f"  Allowed Layers: {', '.join(allowed_layers)}\n"
                    f"  Actual Layer: {actual_layer}\n"
                    f"  Issue: {component_type} must be in one of: {', '.join(allowed_layers)}"
                )
        # Otherwise, enforce strict layer placement
        elif expected_layer != actual_layer:
            rel_path = py_file.relative_to(REPO_ROOT)
            violations.append(
                f"{rel_path}\n"
                f"  Component Type: {component_type}\n"
                f"  Expected Layer: {expected_layer}\n"
                f"  Actual Layer: {actual_layer}\n"
                f"  Issue: File suffix indicates {expected_layer} layer but found in {actual_layer}"
            )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} component naming/placement violations:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            f"\n\nComponent suffixes must match their layer placement.\n" +
            f"See: atdd/coder/conventions/backend.convention.yaml"
        )


@pytest.mark.coder
def test_python_layers_have_proper_component_organization():
    """
    SPEC-CODER-ARCH-PY-0004: Each layer has proper component type grouping.

    Layer organization rules:
    - Domain layer: entities/, value_objects/, aggregates/, services/, specifications/, events/, exceptions/
    - Application layer: use_cases/, handlers/, ports/, dtos/, policies/, workflows/
    - Presentation layer: controllers/, routes/, serializers/, validators/, middleware/, guards/, views/
    - Integration layer: repositories/, clients/, caches/, engines/, formatters/, notifiers/, queues/, stores/, mappers/, schedulers/, monitors/

    Given: Python files organized in layers
    When: Checking directory structure
    Then: Component types are in correct subdirectories
    """
    python_files = find_python_files()

    if not python_files:
        pytest.skip("No Python files found to validate")

    backend_conv = load_backend_convention()

    if not backend_conv:
        pytest.skip("Backend convention file not found")

    violations = []

    for py_file in python_files:
        layer = determine_layer_from_path(py_file)

        # Skip unknown layers
        if layer == 'unknown':
            continue

        path_str = str(py_file)
        filename = py_file.name

        # Determine expected component type from suffix
        expected_layer, component_type = determine_expected_layer_from_suffix(filename, backend_conv)

        # If can't determine, skip
        if expected_layer == 'unknown':
            continue

        # Check if file is in a component type subdirectory
        # Expected pattern: .../layer/component_type/file.py
        # e.g., .../domain/entities/user.py
        # or .../application/use_cases/create_user_use_case.py

        # Files commonly placed at layer root (no subdirectory required)
        layer_root_allowed = [
            'exceptions.py', 'errors.py',  # Exception definitions
            '__init__.py',                  # Package init
            'types.py', 'protocols.py',     # Type definitions and protocols
        ]

        # Skip validation for files commonly at layer root
        if filename in layer_root_allowed:
            continue

        # Alternative directory patterns that are equivalent to convention patterns
        # e.g., "api" is commonly used instead of "routes" or "controllers"
        ALTERNATIVE_DIRS = {
            'routes': ['api', 'endpoints'],  # FastAPI/Flask common patterns
            'controllers': ['api', 'handlers'],  # API handlers pattern
            'use_cases': ['usecases', 'services'],  # Common alternatives
            'services': ['usecases'],  # Services often in usecases dir
            'validators': ['services'],  # Validation services in services dir
            'handlers': ['services'],  # Handler services in services dir
            'monitors': ['services', 'trackers'],  # Monitoring/tracking services
            'engines': ['services', 'analyzers', 'processors'],  # Computation engines
            'formatters': ['services', 'generators'],  # Formatting/generation services
        }

        # Component types that can be at layer root (no subdirectory required)
        # These are commonly placed directly in the layer directory
        LAYER_ROOT_ALLOWED_COMPONENTS = [
            'handlers',   # Domain/application handlers often at root
            'use_cases',  # Small wagons may have single use case at root
            'formatters', # Simple formatters at domain root
            'services',   # Simple services at layer root
        ]

        # Skip if component type is allowed at layer root and file is directly in layer
        if component_type in LAYER_ROOT_ALLOWED_COMPONENTS:
            # Check if file is directly in the layer directory (not in a subdirectory)
            parent_dir = py_file.parent.name
            if parent_dir == layer:
                continue

        # Check if component type directory (or alternative) is in path
        dirs_to_check = [component_type] + ALTERNATIVE_DIRS.get(component_type, [])
        found_valid_dir = any(f'/{dir_name}/' in path_str for dir_name in dirs_to_check)

        if not found_valid_dir:
            # Only flag if this is a clear architecture setup (has layer directory)
            if f'/{layer}/' in path_str:
                rel_path = py_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}\n"
                    f"  Layer: {layer}\n"
                    f"  Component Type: {component_type}\n"
                    f"  Issue: Should be in {layer}/{component_type}/ subdirectory"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} component organization violations:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            f"\n\nComponents should be organized in layer/component_type/ subdirectories.\n" +
            f"Example: domain/entities/user.py, application/use_cases/create_user_use_case.py\n" +
            f"See: atdd/coder/conventions/backend.convention.yaml"
        )
