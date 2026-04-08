"""
Test that Python source files do not contain N+1 query patterns.

Validates:
- No database client calls inside for/while/async for loop bodies
- No database client calls inside list/set/dict comprehensions or generator expressions
- Threshold: 0 (any DB call inside a loop is flagged)

Suppression: Add '# noqa: N+1' on the flagged line to suppress.

Self-contained, no utility dependencies beyond find_repo_root / find_python_dir.
"""

import ast
import pytest
from pathlib import Path
from typing import Dict, List, Optional

from atdd.coach.utils.repo import find_repo_root, find_python_dir


# Path constants
REPO_ROOT = find_repo_root()
PYTHON_DIR = find_python_dir(REPO_ROOT)


# DB client method names that indicate a database call when used as attribute calls.
# These cover: repository pattern, Supabase client, direct DB cursors, GraphQL.
DB_CALL_METHODS = {
    # Repository / ORM pattern
    'execute', 'executemany',
    'fetch', 'fetchone', 'fetchall', 'fetchrow', 'fetchval',
    'find', 'find_one', 'find_many',
    'insert', 'insert_one', 'insert_many',
    'update_one', 'update_many',
    'delete_one', 'delete_many',
    'upsert', 'save', 'aggregate',
    # Supabase chain starters
    'table', 'from_', 'rpc',
    # Direct DB cursor
    'cursor', 'mogrify',
}

# HTTP methods flagged only when called on known HTTP modules.
HTTP_METHODS = {'get', 'post', 'put', 'patch', 'delete', 'request', 'send'}
HTTP_MODULES = {'requests', 'httpx', 'aiohttp'}

# Inline suppression marker
SUPPRESSION_COMMENT = 'noqa: N+1'


def find_python_files() -> List[Path]:
    """Find all Python source files (excluding tests, migrations, __pycache__)."""
    if not PYTHON_DIR.exists():
        return []

    files = []
    for py_file in PYTHON_DIR.rglob("*.py"):
        path_str = str(py_file)
        if '/test/' in path_str or '/tests/' in path_str:
            continue
        if py_file.name.startswith('test_'):
            continue
        if '__pycache__' in path_str:
            continue
        if py_file.name == '__init__.py':
            continue
        if '/migrations/' in path_str:
            continue
        files.append(py_file)

    return files


def _annotate_parents(tree: ast.AST) -> None:
    """Add _parent reference to every node in the AST."""
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child._parent = node


def _find_enclosing_function(node: ast.AST) -> Optional[str]:
    """Walk up _parent chain to find the enclosing function/method name."""
    current = node
    while hasattr(current, '_parent'):
        current = current._parent
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return None


def _is_db_call(node: ast.Call) -> Optional[str]:
    """
    Check if an ast.Call node is a DB client call.

    Returns a human-readable description of the call, or None.
    """
    if isinstance(node.func, ast.Attribute):
        method_name = node.func.attr

        # Tier 1: Direct DB method calls — self.repo.find_one(), db.execute(), etc.
        if method_name in DB_CALL_METHODS:
            return f".{method_name}()"

        # Tier 2: HTTP-as-DB-proxy — only when receiver is a known HTTP module
        if method_name in HTTP_METHODS and isinstance(node.func.value, ast.Name):
            if node.func.value.id in HTTP_MODULES:
                return f"{node.func.value.id}.{method_name}()"

    return None


def _get_loop_body_nodes(loop_node: ast.AST) -> List[ast.AST]:
    """
    Get the body nodes to walk for a loop or comprehension.

    For/While/AsyncFor have a .body list.
    Comprehensions (ListComp, etc.) have .elt/.key/.value and .generators.
    """
    if isinstance(loop_node, (ast.For, ast.While, ast.AsyncFor)):
        return loop_node.body
    if isinstance(loop_node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        return [loop_node.elt] + loop_node.generators
    if isinstance(loop_node, ast.DictComp):
        return [loop_node.key, loop_node.value] + loop_node.generators
    return []


def detect_n_plus_one(file_path: Path) -> List[Dict]:
    """
    Parse a Python file and detect N+1 query patterns.

    Finds DB client calls inside loop bodies (for/while/async for)
    and comprehensions (list/set/dict comp, generator expressions).

    Returns list of violation dicts with keys:
        file, line, function, call, loop_type, loop_line
    """
    try:
        source = file_path.read_text(encoding='utf-8')
    except Exception:
        return []

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    _annotate_parents(tree)
    source_lines = source.splitlines()
    violations = []

    # Node types that represent iteration
    loop_types = (ast.For, ast.While, ast.AsyncFor,
                  ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)

    for node in ast.walk(tree):
        if not isinstance(node, loop_types):
            continue

        # Walk the loop body for Call nodes
        body_nodes = _get_loop_body_nodes(node)
        for body_node in body_nodes:
            for child in ast.walk(body_node):
                if not isinstance(child, ast.Call):
                    continue

                desc = _is_db_call(child)
                if desc is None:
                    continue

                if not hasattr(child, 'lineno'):
                    continue

                # Check for inline suppression
                line_idx = child.lineno - 1
                if 0 <= line_idx < len(source_lines):
                    if SUPPRESSION_COMMENT in source_lines[line_idx]:
                        continue

                func_name = _find_enclosing_function(child) or '<module>'
                loop_type = type(node).__name__
                violations.append({
                    'file': file_path,
                    'line': child.lineno,
                    'function': func_name,
                    'call': desc,
                    'loop_type': loop_type,
                    'loop_line': getattr(node, 'lineno', 0),
                })

    return violations


def scan_query_count(repo_root: Path):
    """Scan for N+1 query patterns. Used by ratchet baseline."""
    python_dir = find_python_dir(repo_root)
    if not python_dir.exists():
        return 0, []
    files = []
    for py_file in python_dir.rglob("*.py"):
        path_str = str(py_file)
        if '/test/' in path_str or '/tests/' in path_str:
            continue
        if py_file.name.startswith('test_') or '__pycache__' in path_str:
            continue
        if py_file.name == '__init__.py' or '/migrations/' in path_str:
            continue
        files.append(py_file)
    all_violations = []
    for py_file in files:
        violations = detect_n_plus_one(py_file)
        for v in violations:
            rel_path = v['file'].relative_to(repo_root)
            all_violations.append(
                f"{rel_path}:{v['line']} {v['function']} {v['call']} in {v['loop_type']}"
            )
    return len(all_violations), all_violations


@pytest.mark.coder
def test_no_db_calls_inside_loops(ratchet_baseline):
    """
    SPEC-CODER-PERF-0001: No database client calls inside loop bodies.

    N+1 query patterns occur when code executes a DB query for each item
    in a collection, instead of batching. This causes O(N) queries where
    O(1) would suffice.

    Given: Python source files in python/ or src/
    When: AST analysis finds DB client calls inside for/while/async for loop bodies
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    python_files = find_python_files()
    if not python_files:
        pytest.skip("No Python source files found")

    count, violations = scan_query_count(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="query_count",
        current_count=count,
        violations=violations,
    )
