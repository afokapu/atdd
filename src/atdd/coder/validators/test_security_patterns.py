"""
Test Python code for known-bad security patterns.

Validates:
- No raw SQL string concatenation in .execute() calls
- FastAPI routes have auth dependency injection
- No hardcoded secrets (AWS keys, private keys, passwords, API keys)

Conventions from:
- atdd/coder/conventions/security.convention.yaml

Rationale: These patterns pretend to be opinions during code review
but are fully encodable as AST/regex rules. Phase 1: AST for SQL
and auth, regex for secrets. Entropy-based detection deferred.
"""

import ast
import fnmatch
import os
import re
import yaml
import pytest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import atdd
from atdd.coach.utils.repo import find_repo_root


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()
PYTHON_DIR = REPO_ROOT / "python"

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
SECURITY_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "security.convention.yaml"

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".dart_tool",
    "build", ".pub-cache", "dist", ".next", ".nuxt", "coverage",
    ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
}


# ---------------------------------------------------------------------------
# Convention loader
# ---------------------------------------------------------------------------
def load_security_convention() -> Dict:
    """Load security convention YAML.  Returns empty dict when missing."""
    if not SECURITY_CONVENTION.exists():
        return {}
    with open(SECURITY_CONVENTION, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
        return data.get("security", {})


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
def matches_exclusion(
    file_path: Path,
    exclusions: List[str],
    base_dir: Path,
) -> bool:
    """Return True if *file_path* matches any exclusion glob relative to *base_dir*."""
    try:
        rel = str(file_path.relative_to(base_dir))
    except ValueError:
        rel = str(file_path)
    return any(fnmatch.fnmatch(rel, pat) for pat in exclusions)


def find_python_files(
    base_dir: Path,
    exclude_patterns: Optional[List[str]] = None,
) -> List[Path]:
    """Walk *base_dir* for ``*.py`` files, honouring skip-dirs and exclusions."""
    if not base_dir.exists():
        return []
    exclude_patterns = exclude_patterns or []
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(base_dir):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            full = Path(dirpath) / fname
            if matches_exclusion(full, exclude_patterns, base_dir):
                continue
            files.append(full)
    return files


def _parse_ast(file_path: Path) -> Optional[ast.Module]:
    """Parse a Python file, returning None on syntax errors."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        return ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return None


# ---------------------------------------------------------------------------
# SQL injection detector  (AST)
# ---------------------------------------------------------------------------
def _contains_sql_keyword(node: ast.expr, keywords: List[str]) -> Optional[str]:
    """Walk an AST expression for string constants containing SQL keywords."""
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            upper = child.value.upper()
            for kw in keywords:
                if kw in upper:
                    return kw
    return None


def check_sql_concatenation(
    file_path: Path,
    sql_keywords: List[str],
    sink_methods: List[str],
) -> List[Dict]:
    """Detect f-string or ``+`` concatenation with SQL keywords inside sink calls."""
    tree = _parse_ast(file_path)
    if tree is None:
        return []

    violations: List[Dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # Match  obj.execute(...)  or  obj.executemany(...)
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in sink_methods):
            continue

        for arg in node.args:
            matched_kw: Optional[str] = None

            # f-string:  f"SELECT ... {var}"
            if isinstance(arg, ast.JoinedStr):
                matched_kw = _contains_sql_keyword(arg, sql_keywords)

            # concatenation:  "SELECT " + var
            elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
                matched_kw = _contains_sql_keyword(arg, sql_keywords)

            if matched_kw:
                violations.append({
                    "file": file_path,
                    "line": arg.lineno,
                    "detail": f"SQL keyword '{matched_kw}' in dynamic string passed to .{func.attr}()",
                })
    return violations


# ---------------------------------------------------------------------------
# Missing auth detector  (AST)
# ---------------------------------------------------------------------------
def _is_route_decorator(
    decorator: ast.expr,
    route_decorators: List[str],
    router_objects: List[str],
) -> bool:
    """Return True if *decorator* looks like ``@router.get(...)``."""
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in route_decorators:
        return False
    # router.get  or  app.post  etc.
    if isinstance(func.value, ast.Name) and func.value.id in router_objects:
        return True
    return False


def _has_auth_dependency(
    func_def: ast.FunctionDef,
    auth_dependencies: List[str],
) -> bool:
    """Return True if any parameter default is ``Depends(auth_fn)``."""
    defaults = list(func_def.args.defaults) + list(func_def.args.kw_defaults)
    for default in defaults:
        if default is None:
            continue
        if not isinstance(default, ast.Call):
            continue
        callee = default.func
        callee_name = None
        if isinstance(callee, ast.Name):
            callee_name = callee.id
        elif isinstance(callee, ast.Attribute):
            callee_name = callee.attr
        if callee_name != "Depends":
            continue
        # Check first positional arg of Depends(...)
        if default.args:
            first = default.args[0]
            if isinstance(first, ast.Name) and first.id in auth_dependencies:
                return True
    return False


def check_missing_auth(
    file_path: Path,
    route_decorators: List[str],
    router_objects: List[str],
    auth_dependencies: List[str],
) -> List[Dict]:
    """Detect FastAPI route functions without auth dependency injection."""
    tree = _parse_ast(file_path)
    if tree is None:
        return []

    violations: List[Dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_route = any(
            _is_route_decorator(d, route_decorators, router_objects)
            for d in node.decorator_list
        )
        if not is_route:
            continue
        if not _has_auth_dependency(node, auth_dependencies):
            violations.append({
                "file": file_path,
                "line": node.lineno,
                "detail": f"Route '{node.name}' has no auth dependency (expected Depends(<auth_fn>))",
            })
    return violations


# ---------------------------------------------------------------------------
# Hardcoded secret detector  (regex)
# ---------------------------------------------------------------------------
def check_hardcoded_secrets(
    file_path: Path,
    patterns: List[Dict],
) -> List[Dict]:
    """Line-by-line regex scan for secret-like strings.  Skips comment lines."""
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    compiled = []
    for pat in patterns:
        flags = 0
        # Case-insensitive for password/token patterns, exact for AWS keys
        if pat["name"] not in ("aws_access_key", "private_key_header"):
            flags = re.IGNORECASE
        compiled.append((pat["name"], re.compile(pat["regex"], flags)))

    violations: List[Dict] = []
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for name, regex in compiled:
            if regex.search(line):
                # Truncate to avoid leaking actual secrets
                snippet = stripped[:60] + ("..." if len(stripped) > 60 else "")
                violations.append({
                    "file": file_path,
                    "line": lineno,
                    "detail": f"Pattern '{name}' matched: {snippet}",
                })
    return violations


# ---------------------------------------------------------------------------
# Violation formatter  (shared across tests)
# ---------------------------------------------------------------------------
def _format_violations(violations: List[Dict], base_dir: Path) -> str:
    """Format violations for pytest.fail() output."""
    lines = []
    for v in violations[:10]:
        try:
            rel = v["file"].relative_to(base_dir)
        except ValueError:
            rel = v["file"]
        lines.append(f"{rel}:{v['line']}\n  {v['detail']}")
    header = f"\n\nFound {len(violations)} security violation(s):\n\n"
    body = "\n\n".join(lines)
    tail = ""
    if len(violations) > 10:
        tail = f"\n\n... and {len(violations) - 10} more"
    return header + body + tail


# ===========================================================================
# Tests
# ===========================================================================

def _violation_strs(violations: List[Dict], base_dir: Path) -> List[str]:
    """Convert violation dicts to string list for ratchet baseline."""
    result = []
    for v in violations:
        try:
            rel = v["file"].relative_to(base_dir)
        except ValueError:
            rel = v["file"]
        result.append(f"{rel}:{v['line']} {v['detail']}")
    return result


def scan_sql_concatenation(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for SQL concatenation violations. Used by ratchet baseline."""
    convention = load_security_convention()
    rule = convention.get("rules", {}).get("sql_injection", {})
    sql_keywords = rule.get("sql_keywords", ["SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE"])
    sink_methods = rule.get("sink_methods", ["execute", "executemany", "raw", "execute_sql"])
    exclusions = rule.get("exclusions", [])
    python_dir = repo_root / "python"
    files = find_python_files(python_dir, exclusions)
    violations: List[Dict] = []
    for f in files:
        violations.extend(check_sql_concatenation(f, sql_keywords, sink_methods))
    return len(violations), _violation_strs(violations, repo_root)


def scan_missing_auth(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for missing auth dependency violations. Used by ratchet baseline."""
    convention = load_security_convention()
    rule = convention.get("rules", {}).get("missing_auth", {})
    route_decorators = rule.get("route_decorators", ["get", "post", "put", "delete", "patch", "options", "head"])
    router_objects = rule.get("router_objects", ["app", "router"])
    auth_deps = rule.get("auth_dependencies", ["get_current_user", "require_auth", "verify_token"])
    exclusions = rule.get("exclusions", [])
    python_dir = repo_root / "python"
    files = find_python_files(python_dir, exclusions)
    violations: List[Dict] = []
    for f in files:
        violations.extend(check_missing_auth(f, route_decorators, router_objects, auth_deps))
    return len(violations), _violation_strs(violations, repo_root)


def scan_hardcoded_secrets(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for hardcoded secrets. Used by ratchet baseline."""
    convention = load_security_convention()
    rule = convention.get("rules", {}).get("hardcoded_secrets", {})
    patterns = rule.get("patterns", [
        {"name": "aws_access_key", "regex": r"AKIA[0-9A-Z]{16}"},
        {"name": "private_key_header", "regex": r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----"},
        {"name": "password_assignment", "regex": r'(password|passwd|pwd)\s*=\s*["\'][^"\']{8,}["\']'},
        {"name": "api_key_assignment", "regex": r'(api_key|apikey|api_secret|secret_key)\s*=\s*["\'][^"\']{8,}["\']'},
        {"name": "generic_token", "regex": r'(token|auth_token|access_token)\s*=\s*["\'][a-zA-Z0-9_\-]{20,}["\']'},
    ])
    exclusions = rule.get("exclusions", [])
    python_dir = repo_root / "python"
    files = find_python_files(python_dir, exclusions)
    violations: List[Dict] = []
    for f in files:
        violations.extend(check_hardcoded_secrets(f, patterns))
    return len(violations), _violation_strs(violations, repo_root)


@pytest.mark.coder
def test_no_raw_sql_concatenation(ratchet_baseline):
    """
    SPEC-CODER-SEC-0001: No raw SQL string concatenation in execute calls.

    SQL injection via f-strings or string concatenation is a critical
    vulnerability.  Parameterized queries must be used instead.

    Given: Python files in python/
    When:  Parsing AST for SQL keywords in dynamic strings passed to sink methods
    Then:  Violation count does not exceed baseline (ratchet pattern)
    """
    files = find_python_files(PYTHON_DIR)
    if not files:
        pytest.skip("No Python files found in python/")

    count, violations = scan_sql_concatenation(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="sql_concatenation",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_fastapi_routes_have_auth_dependency(ratchet_baseline):
    """
    SPEC-CODER-SEC-0002: FastAPI routes must have auth dependency injection.

    Every route handler decorated with @router.get/post/etc must include
    a Depends(auth_function) parameter to enforce authentication.

    Given: Python files in python/ with FastAPI route decorators
    When:  Checking function parameters for Depends(auth_fn)
    Then:  Violation count does not exceed baseline (ratchet pattern)
    """
    files = find_python_files(PYTHON_DIR)
    if not files:
        pytest.skip("No Python files found in python/")

    count, violations = scan_missing_auth(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="missing_auth_dependency",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_no_hardcoded_secrets(ratchet_baseline):
    """
    SPEC-CODER-SEC-0003: No hardcoded secrets in Python source files.

    AWS access keys, private key headers, password assignments, API key
    literals, and bearer tokens must never appear in source code.

    Given: Python files in python/
    When:  Scanning with regex patterns for secret-like strings
    Then:  Violation count does not exceed baseline (ratchet pattern)
    """
    files = find_python_files(PYTHON_DIR)
    if not files:
        pytest.skip("No Python files found in python/")

    count, violations = scan_hardcoded_secrets(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="hardcoded_secrets",
        current_count=count,
        violations=violations,
    )
