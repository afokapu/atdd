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
from typing import List, Optional

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
    'update', 'update_one', 'update_many',
    'delete', 'delete_one', 'delete_many',
    'upsert', 'save', 'count', 'aggregate',
    # Supabase chain starters
    'table', 'from_', 'rpc',
    # Direct DB cursor
    'cursor', 'mogrify',
    # GraphQL
    '_graphql', 'graphql', 'execute_query',
}

# HTTP methods flagged only when called on known HTTP modules.
HTTP_METHODS = {'get', 'post', 'put', 'patch', 'delete', 'request', 'send'}
HTTP_MODULES = {'requests', 'httpx', 'aiohttp'}

# Inline suppression marker
SUPPRESSION_COMMENT = 'noqa: N+1'


# ---------------------------------------------------------------------------
# RED PHASE: Stub — always reports a violation to prove the test can fail.
# This will be replaced with real AST detection in the GREEN phase.
# ---------------------------------------------------------------------------

def find_python_files() -> List[Path]:
    """Find all Python source files (excluding tests, migrations, __pycache__)."""
    if not PYTHON_DIR.exists():
        return []

    files = []
    for py_file in PYTHON_DIR.rglob("*.py"):
        if '/test/' in str(py_file) or '/tests/' in str(py_file):
            continue
        if py_file.name.startswith('test_'):
            continue
        if '__pycache__' in str(py_file):
            continue
        if py_file.name == '__init__.py':
            continue
        if '/migrations/' in str(py_file):
            continue
        files.append(py_file)

    return files


@pytest.mark.coder
def test_no_db_calls_inside_loops():
    """
    SPEC-CODER-PERF-0001: No database client calls inside loop bodies.

    N+1 query patterns occur when code executes a DB query for each item
    in a collection, instead of batching. This causes O(N) queries where
    O(1) would suffice.

    Threshold: 0 (any DB call inside a loop body is flagged)

    Given: Python source files in python/ or src/
    When: AST analysis finds DB client calls inside for/while/async for loop bodies
    Then: Report violations with file, line, function, and call pattern
    """
    # RED stub: unconditionally fail to prove the test harness works
    pytest.fail(
        "\\n\\nRED PHASE: N+1 query detector not yet implemented.\\n"
        "This test will be replaced with AST-based detection in GREEN phase."
    )
