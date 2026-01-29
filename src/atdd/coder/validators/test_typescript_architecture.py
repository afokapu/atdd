"""
Test TypeScript code follows clean architecture and naming conventions.

Validates:
- Domain layer is pure (no imports from other layers)
- Application layer only imports from domain
- Presentation layer imports from application/domain
- Integration layer only imports from domain
- Component naming follows frontend/backend conventions
- Files are in correct layers based on their suffixes

Conventions from:
- atdd/coder/conventions/frontend.convention.yaml
- atdd/coder/conventions/backend.convention.yaml

Inspired by: .claude/utils/coder/architecture.py
But: Self-contained, no utility dependencies
"""

import pytest
import re
import yaml
from pathlib import Path
from typing import Dict, List, Set, Tuple


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
TS_DIRS = [
    REPO_ROOT / "supabase" / "functions",
    REPO_ROOT / "typescript",
    REPO_ROOT / "frontend",
    REPO_ROOT / "web",
]
FRONTEND_CONVENTION = REPO_ROOT / "atdd" / "coder" / "conventions" / "frontend.convention.yaml"
BACKEND_CONVENTION = REPO_ROOT / "atdd" / "coder" / "conventions" / "backend.convention.yaml"


def load_conventions() -> Tuple[Dict, Dict]:
    """
    Load frontend and backend conventions from YAML files.

    Returns:
        Tuple of (frontend_convention, backend_convention) dicts
    """
    frontend = {}
    backend = {}

    if FRONTEND_CONVENTION.exists():
        with open(FRONTEND_CONVENTION, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            frontend = data.get('frontend', {})

    if BACKEND_CONVENTION.exists():
        with open(BACKEND_CONVENTION, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            backend = data.get('backend', {})

    return frontend, backend


def get_layer_component_suffixes(conventions: Dict) -> Dict[str, Dict[str, List[str]]]:
    """
    Extract layer -> component_type -> suffixes mapping from conventions.

    Args:
        conventions: Frontend or backend convention dict

    Returns:
        Dict like {
            'domain': {
                'entities': ['*.ts', '*-entity.ts'],
                'value_objects': ['*-vo.ts', '*.ts']
            },
            'application': {...},
            ...
        }
    """
    result = {}

    layers = conventions.get('layers', {})
    for layer_name, layer_config in layers.items():
        result[layer_name] = {}

        component_types = layer_config.get('component_types', [])
        for component_type in component_types:
            name = component_type.get('name', '')
            suffix_config = component_type.get('suffix', {})

            # Get TypeScript suffixes
            ts_suffixes = suffix_config.get('typescript', '')
            if ts_suffixes:
                # Parse comma-separated suffixes
                suffixes = [s.strip() for s in ts_suffixes.split(',')]
                result[layer_name][name] = suffixes

    return result


def determine_layer_from_path(file_path: Path) -> str:
    """
    Determine layer from file path.

    Args:
        file_path: Path to TypeScript file

    Returns:
        Layer name: 'domain', 'application', 'presentation', 'integration', 'unknown'
    """
    path_str = str(file_path).lower()

    # Check explicit layer directories
    if '/domain/' in path_str or path_str.endswith('/domain.ts'):
        return 'domain'
    elif '/application/' in path_str or path_str.endswith('/application.ts'):
        return 'application'
    elif '/presentation/' in path_str or path_str.endswith('/presentation.ts'):
        return 'presentation'
    elif '/integration/' in path_str or '/infrastructure/' in path_str:
        return 'integration'

    # Check alternative patterns
    if '/entities/' in path_str or '/models/' in path_str or '/value_objects/' in path_str:
        return 'domain'
    elif '/use_cases/' in path_str or '/usecases/' in path_str or '/handlers/' in path_str:
        return 'application'
    elif '/controllers/' in path_str or '/views/' in path_str or '/components/' in path_str:
        return 'presentation'
    elif '/adapters/' in path_str or '/repositories/' in path_str or '/clients/' in path_str:
        return 'integration'

    return 'unknown'


def extract_typescript_imports(file_path: Path) -> List[str]:
    """
    Extract import statements from TypeScript file.

    Args:
        file_path: Path to TypeScript file

    Returns:
        List of imported module paths
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    imports = []

    # Match: import { X } from 'Y'
    from_imports = re.findall(r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]", content)
    imports.extend(from_imports)

    # Match: import 'X'
    direct_imports = re.findall(r"import\s+['\"]([^'\"]+)['\"]", content)
    imports.extend(direct_imports)

    # Match: const X = require('Y')
    require_imports = re.findall(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", content)
    imports.extend(require_imports)

    return imports


def infer_layer_from_import(import_path: str) -> str:
    """
    Infer layer from import path.

    Args:
        import_path: Import statement (e.g., "./domain/entities/user")

    Returns:
        Layer name or 'external' for third-party imports
    """
    import_lower = import_path.lower()

    # Check for layer indicators in import path
    if 'domain' in import_lower and ('entities' in import_lower or 'models' in import_lower or 'value_objects' in import_lower):
        return 'domain'
    elif 'application' in import_lower or 'use_case' in import_lower or 'usecase' in import_lower:
        return 'application'
    elif 'presentation' in import_lower or 'controller' in import_lower or 'component' in import_lower or 'view' in import_lower:
        return 'presentation'
    elif 'integration' in import_lower or 'infrastructure' in import_lower or 'adapter' in import_lower or 'repository' in import_lower or 'client' in import_lower:
        return 'integration'

    # Check if it's a relative import
    if import_path.startswith('.'):
        return 'unknown'

    # Third-party or external (http://, https://, npm:, node:)
    if import_path.startswith(('http://', 'https://', 'npm:', 'node:', '@')):
        return 'external'

    # Standard Deno imports
    if 'deno.land' in import_path or 'esm.sh' in import_path:
        return 'external'

    # Third-party or standard library
    return 'external'


def find_typescript_files() -> List[Path]:
    """
    Find all TypeScript files in configured directories.

    Returns:
        List of Path objects
    """
    ts_files = []

    for ts_dir in TS_DIRS:
        if not ts_dir.exists():
            continue

        for ts_file in ts_dir.rglob("*.ts"):
            # Skip test files
            if '/test/' in str(ts_file) or ts_file.name.startswith('test_'):
                continue
            # Skip .test.ts
            if ts_file.name.endswith('.test.ts'):
                continue
            # Skip node_modules
            if 'node_modules' in str(ts_file):
                continue
            # Skip .d.ts (type definitions)
            if ts_file.name.endswith('.d.ts'):
                continue

            ts_files.append(ts_file)

    return ts_files


def matches_suffix_pattern(filename: str, pattern: str) -> bool:
    """
    Check if filename matches a suffix pattern.

    Args:
        filename: File name (e.g., "user-service.ts")
        pattern: Pattern (e.g., "*-service.ts")

    Returns:
        True if matches
    """
    # Convert glob pattern to regex
    # *-service.ts -> .*-service\.ts$
    # *.ts -> .*\.ts$
    regex_pattern = pattern.replace('.', r'\.')
    regex_pattern = regex_pattern.replace('*', '.*')
    regex_pattern = f'^{regex_pattern}$'

    return bool(re.match(regex_pattern, filename))


def determine_expected_layer_from_suffix(filename: str, conventions: Dict) -> Tuple[str, str]:
    """
    Determine expected layer and component type from filename suffix.

    Args:
        filename: File name (e.g., "user-service.ts")
        conventions: Frontend or backend convention dict

    Returns:
        Tuple of (layer_name, component_type) or ('unknown', 'unknown')
    """
    layer_suffixes = get_layer_component_suffixes(conventions)

    # First pass: check more specific patterns (skip generic *.ts)
    for layer_name, component_types in layer_suffixes.items():
        for component_type, suffixes in component_types.items():
            # Sort suffixes by length descending (more specific first)
            sorted_suffixes = sorted(suffixes, key=len, reverse=True)
            for suffix_pattern in sorted_suffixes:
                # Skip generic patterns
                if suffix_pattern in ('*.ts', '*.tsx'):
                    continue
                if matches_suffix_pattern(filename, suffix_pattern):
                    return layer_name, component_type

    # Don't fall back to generic *.ts - causes too many false positives
    return 'unknown', 'unknown'


def is_frontend_file(file_path: Path) -> bool:
    """Check if file is in frontend (web/) directory."""
    path_str = str(file_path)
    return '/web/' in path_str or path_str.startswith('web/')


@pytest.mark.coder
def test_typescript_follows_clean_architecture():
    """
    SPEC-CODER-ARCH-TS-0001: TypeScript code follows 4-layer clean architecture.

    Dependency rules differ by context:

    Frontend (web/) - per frontend.convention.yaml:
    - Domain → NOTHING (domain must be pure)
    - Application → Domain, Integration (hooks can orchestrate both)
    - Presentation → Application, Domain
    - Integration → Application, Domain

    Backend (supabase/) - per backend.convention.yaml:
    - Domain → NOTHING (domain must be pure)
    - Application → Domain only (use ports for integration)
    - Presentation → Application, Domain
    - Integration → Application, Domain

    Given: TypeScript files in web/, supabase/functions/, etc.
    When: Checking import statements
    Then: No forbidden cross-layer dependencies per context
    """
    ts_files = find_typescript_files()

    if not ts_files:
        pytest.skip("No TypeScript files found to validate")

    violations = []

    for ts_file in ts_files:
        layer = determine_layer_from_path(ts_file)

        # Skip files we can't categorize
        if layer == 'unknown':
            continue

        imports = extract_typescript_imports(ts_file)
        is_frontend = is_frontend_file(ts_file)

        for imp in imports:
            target_layer = infer_layer_from_import(imp)

            # Skip external imports (third-party libraries)
            if target_layer == 'external' or target_layer == 'unknown':
                continue

            # Check dependency rules
            violation = None

            if layer == 'domain':
                # Domain must not import from any other layer (both frontend and backend)
                if target_layer in ['application', 'presentation', 'integration']:
                    violation = f"Domain layer cannot import from {target_layer}"

            elif layer == 'application':
                if is_frontend:
                    # Frontend: application CAN import integration (hooks orchestrate both)
                    # See frontend.convention.yaml: application -> [domain, integration]
                    if target_layer == 'presentation':
                        violation = f"Application layer cannot import from {target_layer}"
                else:
                    # Backend: application can only import from domain (use ports)
                    if target_layer in ['presentation', 'integration']:
                        violation = f"Application layer cannot import from {target_layer}"

            elif layer == 'integration':
                # Integration can import from application (for ports) and domain
                if target_layer == 'presentation':
                    violation = f"Integration layer cannot import from {target_layer}"

            if violation:
                rel_path = ts_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}\n"
                    f"  Layer: {layer}\n"
                    f"  Import: {imp}\n"
                    f"  Violation: {violation}"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} architecture violations:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )


@pytest.mark.coder
def test_typescript_domain_layer_is_pure():
    """
    SPEC-CODER-ARCH-TS-0002: TypeScript domain layer has no external dependencies.

    Domain layer should only import:
    - Standard library (no third-party)
    - Other domain modules

    Should NOT import:
    - Third-party libraries (except type definitions)
    - Application/Presentation/Integration layers
    - Database/API libraries
    - Deno/Node runtime libraries

    Given: TypeScript files in domain/ directories
    When: Checking imports
    Then: Only standard imports and domain imports
    """
    ts_files = find_typescript_files()

    if not ts_files:
        pytest.skip("No TypeScript files found to validate")

    # Allowed imports in domain layer
    # Internal domain path aliases are allowed (e.g., @commons/domain)
    ALLOWED_DOMAIN_IMPORTS = {
        '@commons/domain',  # Shared domain types and pure functions
    }

    violations = []

    for ts_file in ts_files:
        layer = determine_layer_from_path(ts_file)

        # Only check domain layer
        if layer != 'domain':
            continue

        imports = extract_typescript_imports(ts_file)

        for imp in imports:
            # Skip relative imports (internal to domain)
            if imp.startswith('.'):
                continue

            # Check if it's external/third-party
            if imp.startswith(('http://', 'https://', 'npm:', 'node:', '@')) or 'deno.land' in imp or 'esm.sh' in imp:
                # Check if it's an allowed domain import (internal path alias)
                if any(imp.startswith(allowed) for allowed in ALLOWED_DOMAIN_IMPORTS):
                    continue
                rel_path = ts_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}\n"
                    f"  Import: {imp}\n"
                    f"  Issue: Domain layer should not import external libraries"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} domain purity violations:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            f"\n\nDomain layer should only import:\n" +
            f"  - Other domain modules (relative imports)\n" +
            f"  - Type definitions only (if necessary)"
        )


@pytest.mark.coder
def test_typescript_component_naming_follows_conventions():
    """
    SPEC-CODER-ARCH-TS-0003: TypeScript components follow naming conventions.

    Component naming rules from conventions:
    - Controllers: *-controller.ts (presentation layer)
    - Services: *-service.ts (domain layer)
    - Repositories: *-repository.ts (integration layer)
    - Use Cases: *-use-case.ts (application layer)
    - Entities: *.ts or *-entity.ts (domain layer)
    - DTOs: *-dto.ts (application layer)
    - Validators: *-validator.ts (presentation/integration layer)
    - Mappers: *-mapper.ts (integration layer)
    - Clients: *-client.ts or *-api.ts (integration layer)
    - Stores: *-store.ts (integration layer)
    - Handlers: *-handler.ts (application layer)
    - Guards: *-guard.ts (presentation layer)
    - Middleware: *-middleware.ts (presentation layer)
    - Ports: *-port.ts or *-interface.ts (application layer)
    - Events: *-event.ts (domain layer)
    - Exceptions: *-exception.ts or exceptions.ts (domain layer)

    Given: TypeScript files with recognizable suffixes
    When: Checking file locations
    Then: Files are in correct layers per their suffixes
    """
    ts_files = find_typescript_files()

    if not ts_files:
        pytest.skip("No TypeScript files found to validate")

    frontend_conv, backend_conv = load_conventions()

    violations = []

    for ts_file in ts_files:
        actual_layer = determine_layer_from_path(ts_file)

        # Skip files in unknown locations
        if actual_layer == 'unknown':
            continue

        filename = ts_file.name

        # Check against backend conventions
        expected_layer, component_type = determine_expected_layer_from_suffix(filename, backend_conv)

        # If not found in backend, try frontend
        if expected_layer == 'unknown':
            expected_layer, component_type = determine_expected_layer_from_suffix(filename, frontend_conv)

        # If we found an expected layer and it doesn't match actual
        if expected_layer != 'unknown' and expected_layer != actual_layer:
            rel_path = ts_file.relative_to(REPO_ROOT)
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
            f"See:\n" +
            f"  - atdd/coder/conventions/frontend.convention.yaml\n" +
            f"  - atdd/coder/conventions/backend.convention.yaml"
        )


@pytest.mark.coder
def test_typescript_layers_have_proper_component_organization():
    """
    SPEC-CODER-ARCH-TS-0004: Each layer has proper component type grouping.

    Layer organization rules:
    - Domain layer: entities/, value_objects/, services/, specifications/, events/, exceptions/
    - Application layer: use_cases/, handlers/, ports/, dtos/, policies/, workflows/
    - Presentation layer: controllers/, routes/, serializers/, validators/, middleware/, guards/, views/
    - Integration layer: repositories/, clients/, caches/, engines/, formatters/, notifiers/, queues/, stores/, mappers/, schedulers/, monitors/

    Given: TypeScript files organized in layers
    When: Checking directory structure
    Then: Component types are in correct subdirectories
    """
    ts_files = find_typescript_files()

    if not ts_files:
        pytest.skip("No TypeScript files found to validate")

    frontend_conv, backend_conv = load_conventions()

    # Build expected component type directories per layer
    backend_layer_components = get_layer_component_suffixes(backend_conv)
    frontend_layer_components = get_layer_component_suffixes(frontend_conv)

    violations = []

    for ts_file in ts_files:
        layer = determine_layer_from_path(ts_file)

        # Skip unknown layers
        if layer == 'unknown':
            continue

        path_str = str(ts_file)
        filename = ts_file.name

        # Determine expected component type from suffix
        expected_layer_backend, component_type_backend = determine_expected_layer_from_suffix(filename, backend_conv)
        expected_layer_frontend, component_type_frontend = determine_expected_layer_from_suffix(filename, frontend_conv)

        # Use whichever matched
        if expected_layer_backend != 'unknown':
            expected_layer = expected_layer_backend
            component_type = component_type_backend
        elif expected_layer_frontend != 'unknown':
            expected_layer = expected_layer_frontend
            component_type = component_type_frontend
        else:
            # Can't determine component type
            continue

        # Check if file is in a component type subdirectory
        # Expected pattern: .../layer/component_type/file.ts
        # e.g., .../domain/entities/user.ts
        # or .../application/use_cases/create-user-use-case.ts

        # Files commonly placed at layer root (no subdirectory required)
        layer_root_allowed = [
            'exceptions.ts', 'errors.ts',  # Exception definitions
            'types.ts', 'index.ts',         # Type definitions and barrel exports
        ]

        # Skip validation for files commonly at layer root
        if filename in layer_root_allowed:
            continue

        # Check if component type directory is in path
        if f'/{component_type}/' not in path_str:
            # Only flag if this is a clear architecture setup (has layer directory)
            if f'/{layer}/' in path_str:
                rel_path = ts_file.relative_to(REPO_ROOT)
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
            f"Example: domain/entities/user.ts, application/use_cases/create-user-use-case.ts\n" +
            f"See:\n" +
            f"  - atdd/coder/conventions/frontend.convention.yaml\n" +
            f"  - atdd/coder/conventions/backend.convention.yaml"
        )
