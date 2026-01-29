"""
Test import boundaries are enforced across layers.

Validates:
- No circular dependencies between modules
- Imports follow dependency flow (inward)
- No imports from test code into production code

Inspired by: .claude/utils/coder/import_scan.py
But: Self-contained, no utility dependencies
"""

import pytest
import re
from pathlib import Path
from typing import Dict, List, Set


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = REPO_ROOT / "python"


def extract_all_imports(file_path: Path) -> List[str]:
    """
    Extract all import statements from Python file.

    Args:
        file_path: Path to Python file

    Returns:
        List of imported module names
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

    # Match: import X, Y, Z
    direct_imports = re.findall(r'^\s*import\s+([^\s;#]+)', content, re.MULTILINE)
    for imp in direct_imports:
        # Split comma-separated imports
        imports.extend([i.strip() for i in imp.split(',')])

    return imports


def is_internal_import(import_path: str, base_module: str) -> bool:
    """
    Check if import is internal to the project.

    Args:
        import_path: Import statement
        base_module: Base module name to check against

    Returns:
        True if import is internal to project
    """
    # Relative imports
    if import_path.startswith('.'):
        return True

    # Absolute imports from same base module
    if import_path.startswith(base_module):
        return True

    # Check if it's from python/ directory structure
    if 'pace_dilemmas' in import_path or 'juggle_domains' in import_path:
        return True

    return False


def get_module_name(file_path: Path) -> str:
    """
    Get module name from file path.

    Args:
        file_path: Path to Python file

    Returns:
        Module name (e.g., "pace_dilemmas.pair_fragments.domain.entities")
    """
    try:
        rel_path = file_path.relative_to(PYTHON_DIR)
        # Remove .py extension
        module_path = str(rel_path).replace('.py', '')
        # Convert path to module name
        module_name = module_path.replace('/', '.')
        # Remove src. prefix if present
        if '.src.' in module_name:
            module_name = module_name.replace('.src.', '.')
        return module_name
    except ValueError:
        return str(file_path.stem)


def find_python_modules() -> List[Path]:
    """
    Find all Python modules (excluding tests).

    Returns:
        List of Path objects
    """
    if not PYTHON_DIR.exists():
        return []

    modules = []
    for py_file in PYTHON_DIR.rglob("*.py"):
        # Skip test files
        if '/test/' in str(py_file) or py_file.name.startswith('test_'):
            continue
        # Skip __pycache__
        if '__pycache__' in str(py_file):
            continue

        modules.append(py_file)

    return modules


def build_dependency_graph() -> Dict[str, Set[str]]:
    """
    Build dependency graph of all Python modules.

    Returns:
        Dict mapping module names to their dependencies
    """
    graph = {}

    for module_file in find_python_modules():
        module_name = get_module_name(module_file)
        imports = extract_all_imports(module_file)

        # Filter to internal imports only
        internal_imports = {
            imp for imp in imports
            if is_internal_import(imp, 'pace_dilemmas') or is_internal_import(imp, 'juggle_domains')
        }

        graph[module_name] = internal_imports

    return graph


def find_circular_dependencies(graph: Dict[str, Set[str]]) -> List[tuple]:
    """
    Find circular dependencies in module graph.

    Args:
        graph: Dependency graph

    Returns:
        List of (module_a, module_b) tuples representing circular deps
    """
    circular = []

    for module, deps in graph.items():
        for dep in deps:
            # Check if dep also imports module (direct circular)
            if dep in graph and module in graph[dep]:
                # Only report each circle once (canonical order)
                if module < dep:
                    circular.append((module, dep))

    return circular


def find_cycles(graph: Dict[str, Set[str]], max_depth: int = 5) -> List[List[str]]:
    """
    Find dependency cycles using DFS.

    Args:
        graph: Dependency graph
        max_depth: Maximum cycle length to detect

    Returns:
        List of cycles (each cycle is a list of module names)
    """
    cycles = []

    def dfs(node, path, visited):
        if node in path:
            # Found a cycle
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            if len(cycle) <= max_depth:
                # Normalize cycle (start with smallest element)
                min_idx = cycle.index(min(cycle))
                normalized = cycle[min_idx:] + cycle[:min_idx]
                if normalized not in cycles:
                    cycles.append(normalized)
            return

        if node in visited or node not in graph:
            return

        visited.add(node)
        path.append(node)

        for neighbor in graph.get(node, set()):
            dfs(neighbor, path, visited)

        path.pop()

    for start_node in graph.keys():
        dfs(start_node, [], set())

    return cycles


@pytest.mark.coder
def test_no_circular_module_dependencies():
    """
    SPEC-CODER-IMPORT-0001: No circular dependencies between modules.

    Circular dependencies cause:
    - Import errors
    - Initialization issues
    - Tight coupling
    - Difficult testing

    Given: All Python modules in python/
    When: Building dependency graph
    Then: No module imports another that imports it back
    """
    graph = build_dependency_graph()

    if not graph:
        pytest.skip("No Python modules found to validate")

    # Find direct circular dependencies (A → B, B → A)
    circular = find_circular_dependencies(graph)

    if circular:
        pytest.fail(
            f"\\n\\nFound {len(circular)} circular dependencies:\\n\\n" +
            "\\n".join(f"  {a} ↔ {b}" for a, b in circular[:10]) +
            (f"\\n  ... and {len(circular) - 10} more" if len(circular) > 10 else "")
        )


@pytest.mark.coder
def test_no_import_cycles():
    """
    SPEC-CODER-IMPORT-0002: No dependency cycles (A → B → C → A).

    Dependency cycles create:
    - Complex initialization order
    - Difficult refactoring
    - Testing challenges
    - Code smell

    Given: All Python modules
    When: Analyzing dependency chains
    Then: No module depends on itself through intermediaries
    """
    graph = build_dependency_graph()

    if not graph:
        pytest.skip("No Python modules found to validate")

    cycles = find_cycles(graph, max_depth=5)

    if cycles:
        # Format cycles for display
        formatted_cycles = []
        for cycle in cycles[:5]:  # Show first 5
            chain = " → ".join(cycle)
            formatted_cycles.append(f"  {chain}")

        pytest.fail(
            f"\\n\\nFound {len(cycles)} dependency cycles:\\n\\n" +
            "\\n".join(formatted_cycles) +
            (f"\\n  ... and {len(cycles) - 5} more" if len(cycles) > 5 else "") +
            f"\\n\\nCycles create tight coupling and make refactoring difficult."
        )


@pytest.mark.coder
def test_no_test_imports_in_production():
    """
    SPEC-CODER-IMPORT-0003: Production code doesn't import from test code.

    Test code can import production code, but NOT vice versa.

    Given: All Python production modules
    When: Checking imports
    Then: No imports from test/ directories
    """
    violations = []

    for module_file in find_python_modules():
        # Skip if this is already a test file
        if '/test/' in str(module_file):
            continue

        imports = extract_all_imports(module_file)

        for imp in imports:
            # Check if importing from test directory
            if '/test/' in imp or imp.startswith('test_') or '.test.' in imp:
                rel_path = module_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}\\n"
                    f"  Import: {imp}\\n"
                    f"  Issue: Production code imports from test code"
                )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} test import violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            f"\\n\\nProduction code should never import test code."
        )


@pytest.mark.coder
def test_imports_follow_layer_boundaries():
    """
    SPEC-CODER-IMPORT-0004: Imports respect architectural boundaries.

    Based on file path structure:
    - domain/ can only import from domain/
    - application/ can import from domain/, application/
    - integration/ can import from domain/, integration/
    - presentation/ can import from domain/, application/, presentation/

    Given: All Python modules with layer structure
    When: Checking imports
    Then: Imports only from allowed layers
    """
    violations = []

    for module_file in find_python_modules():
        module_path = str(module_file)

        # Determine this module's layer
        if '/domain/' in module_path:
            current_layer = 'domain'
            allowed_layers = ['domain']
        elif '/application/' in module_path:
            current_layer = 'application'
            allowed_layers = ['domain', 'application']
        elif '/integration/' in module_path or '/infrastructure/' in module_path:
            current_layer = 'integration'
            allowed_layers = ['domain', 'integration', 'infrastructure']
        elif '/presentation/' in module_path:
            current_layer = 'presentation'
            allowed_layers = ['domain', 'application', 'presentation']
        else:
            # Can't determine layer, skip
            continue

        imports = extract_all_imports(module_file)

        for imp in imports:
            # Skip external imports
            if not (is_internal_import(imp, 'pace_dilemmas') or is_internal_import(imp, 'juggle_domains')):
                continue

            # Check if import crosses boundary
            import_layer = None
            if '/domain/' in imp or '.domain.' in imp:
                import_layer = 'domain'
            elif '/application/' in imp or '.application.' in imp:
                import_layer = 'application'
            elif '/integration/' in imp or '/infrastructure/' in imp or '.integration.' in imp:
                import_layer = 'integration'
            elif '/presentation/' in imp or '.presentation.' in imp:
                import_layer = 'presentation'

            if import_layer and import_layer not in allowed_layers:
                rel_path = module_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}\\n"
                    f"  Layer: {current_layer}\\n"
                    f"  Import: {imp}\\n"
                    f"  Target layer: {import_layer}\\n"
                    f"  Violation: {current_layer} cannot import from {import_layer}"
                )

    if violations:
        pytest.fail(
            f"\\n\\nFound {len(violations)} boundary violations:\\n\\n" +
            "\\n\\n".join(violations[:10]) +
            (f"\\n\\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )
