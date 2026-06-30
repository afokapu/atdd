"""python-pytest detector for coder.security.sql-injection (+ -missing-auth, -hardcoded-secret).

Realizes the agnostic security-pattern obligations for the PYTHON stack (all three
rule_ids disposition `strict`):

  * coder.security.sql-injection   — a SQL keyword inside an f-string / `+`
    concatenation passed to a database sink call (`.execute` / `.executemany` /
    `.raw` / `.execute_sql`).            [AST]
  * coder.security.missing-auth    — a FastAPI route function (`@router.get` …)
    whose parameter defaults carry no `Depends(<auth_fn>)`.   [AST]
  * coder.security.hardcoded-secret — a line matching a known secret shape (AWS
    key, PEM private-key header, password / api_key / token assignment). [regex]

ONE run carries THREE distinct rule_ids — the v1.1 multi-rule output channel
(PROVIDER-CONTRACT-v1.1.md §3).

PROVENANCE — ported from core
    src/atdd/coder/validators/test_security_patterns.py
        :: check_sql_concatenation / _contains_sql_keyword
           / check_missing_auth / _is_route_decorator / _has_auth_dependency
           / check_hardcoded_secrets / find_python_files / matches_exclusion
    (blob adbd0043c6765802). The AST/regex detection is copied behavior-for-behavior;
    the `atdd.coach.*` substrate couplings were REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_SQL`` / ``RULE_AUTH`` /
    ``RULE_SECRET`` constants. Authoritative metadata (severity 5; all strict)
    lives in the convention nodes.
  * ``Violation``  -> plain dicts in the v1.1 shape
    ``{rule_id, file, line, col, evidence, source_line}`` (§3.2). The core
    ``location`` + ``detail`` are preserved inside ``file`` (scan-root-relative
    path), ``line``/``col`` (AST positions; regex match position) and ``evidence``.
  * ``find_repo_root`` + ``REPO_ROOT / "python"`` single-dir scan -> REMOVED. Each
    ``ATDD_SCAN_ROOTS`` entry is scanned directly for ``*.py`` and the offending
    ``file`` is reported relative to that root (§2). Exclusion globs arrive via
    ``ATDD_SCAN_EXCLUDES`` rather than being read from a convention/config (§2).
  * The ``security.convention.yaml`` rule config (sql_keywords / sink_methods /
    route_decorators / router_objects / auth_dependencies / secret patterns)
    -> VENDORED as the module constants below (copied verbatim from the
    convention, blob a63b6862a146e7df), so the detector needs no YAML load.
  * ``assert_disposition_satisfied`` (ratchet baseline) -> NOT PORTED; all three
    rule_ids are strict, aggregated downstream by the consumer (§1).

Pure stdlib (``ast``, ``re``, ``fnmatch``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import ast
import fnmatch
import re
from pathlib import Path

RULE_SQL = "coder.security.sql-injection"        # disposition: strict
RULE_AUTH = "coder.security.missing-auth"         # disposition: strict
RULE_SECRET = "coder.security.hardcoded-secret"   # disposition: strict

# Directories the core walk skipped (verbatim).
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".dart_tool",
    "build", ".pub-cache", "dist", ".next", ".nuxt", "coverage",
    ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
}

# Vendored from security.convention.yaml -> security.rules (verbatim).
SQL_KEYWORDS = ("SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE")
SINK_METHODS = ("execute", "executemany", "raw", "execute_sql")

ROUTE_DECORATORS = ("get", "post", "put", "delete", "patch", "options", "head")
ROUTER_OBJECTS = ("app", "router")
AUTH_DEPENDENCIES = ("get_current_user", "require_auth", "verify_token", "get_authenticated_user")

# (name, regex). aws_access_key / private_key_header are case-SENSITIVE; the rest
# match case-insensitively — mirrored verbatim from the source validator.
SECRET_PATTERNS = (
    ("aws_access_key", r"AKIA[0-9A-Z]{16}", False),
    ("private_key_header", r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----", False),
    ("password_assignment", r'(password|passwd|pwd)\s*=\s*["\'][^"\']{8,}["\']', True),
    ("api_key_assignment", r'(api_key|apikey|api_secret|secret_key)\s*=\s*["\'][^"\']{8,}["\']', True),
    ("generic_token", r'(token|auth_token|access_token)\s*=\s*["\'][a-zA-Z0-9_\-]{20,}["\']', True),
)
_COMPILED_SECRETS = tuple(
    (name, re.compile(rx, re.IGNORECASE if ci else 0)) for name, rx, ci in SECRET_PATTERNS
)


# ── file discovery (ported behavior-for-behavior) ─────────────────────────────


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _matches_exclusion(path: Path, root: Path, exclude_globs: list[str]) -> bool:
    rel = _rel(root, path)
    return any(fnmatch.fnmatch(rel, pat) for pat in exclude_globs)


def find_python_files(root: Path, exclude_globs: list[str] | None = None) -> list[Path]:
    """Walk ``root`` for ``*.py`` files, honoring skip-dirs and exclusion globs."""
    if not root.exists():
        return []
    exclude_globs = exclude_globs or []
    files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if _matches_exclusion(path, root, exclude_globs):
            continue
        files.append(path)
    return files


def _parse_ast(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _source_line(lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


# ── SQL injection detector (AST, ported) ──────────────────────────────────────


def _contains_sql_keyword(node: ast.expr) -> str | None:
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            upper = child.value.upper()
            for kw in SQL_KEYWORDS:
                if kw in upper:
                    return kw
    return None


def check_sql_concatenation(root: Path, path: Path, tree: ast.Module, lines: list[str]) -> list[dict]:
    violations: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in SINK_METHODS):
            continue
        for arg in node.args:
            matched_kw: str | None = None
            if isinstance(arg, ast.JoinedStr):
                matched_kw = _contains_sql_keyword(arg)
            elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
                matched_kw = _contains_sql_keyword(arg)
            if matched_kw:
                violations.append({
                    "rule_id": RULE_SQL,
                    "file": _rel(root, path),
                    "line": arg.lineno,
                    "col": arg.col_offset,
                    "evidence": (
                        f"SQL keyword '{matched_kw}' in dynamic string passed to "
                        f".{func.attr}() — use a parameterized query"
                    ),
                    "source_line": _source_line(lines, arg.lineno),
                })
    return violations


# ── missing auth detector (AST, ported) ───────────────────────────────────────


def _is_route_decorator(decorator: ast.expr) -> bool:
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in ROUTE_DECORATORS:
        return False
    return isinstance(func.value, ast.Name) and func.value.id in ROUTER_OBJECTS


def _has_auth_dependency(func_def) -> bool:
    defaults = list(func_def.args.defaults) + list(func_def.args.kw_defaults)
    for default in defaults:
        if default is None or not isinstance(default, ast.Call):
            continue
        callee = default.func
        callee_name = None
        if isinstance(callee, ast.Name):
            callee_name = callee.id
        elif isinstance(callee, ast.Attribute):
            callee_name = callee.attr
        if callee_name != "Depends":
            continue
        if default.args:
            first = default.args[0]
            if isinstance(first, ast.Name) and first.id in AUTH_DEPENDENCIES:
                return True
    return False


def check_missing_auth(root: Path, path: Path, tree: ast.Module, lines: list[str]) -> list[dict]:
    violations: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(_is_route_decorator(d) for d in node.decorator_list):
            continue
        if _has_auth_dependency(node):
            continue
        violations.append({
            "rule_id": RULE_AUTH,
            "file": _rel(root, path),
            "line": node.lineno,
            "col": node.col_offset,
            "evidence": (
                f"Route '{node.name}' has no auth dependency "
                f"(expected a Depends(<auth_fn>) parameter)"
            ),
            "source_line": _source_line(lines, node.lineno),
        })
    return violations


# ── hardcoded secret detector (regex, ported) ─────────────────────────────────


def check_hardcoded_secrets(root: Path, path: Path, lines: list[str]) -> list[dict]:
    violations: list[dict] = []
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for name, regex in _COMPILED_SECRETS:
            m = regex.search(line)
            if m:
                # Truncate so the actual secret value is not echoed in full.
                snippet = stripped[:60] + ("..." if len(stripped) > 60 else "")
                violations.append({
                    "rule_id": RULE_SECRET,
                    "file": _rel(root, path),
                    "line": lineno,
                    "col": m.start(),
                    "evidence": f"Pattern '{name}' matched a secret-shaped literal: {snippet}",
                    "source_line": line,
                })
    return violations


# ── public scan API (the v1.1 contract surface) ───────────────────────────────


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one python stack ``root`` and return RAW v1.1 violation dicts.

    Emits all three rule_ids — SQL injection + missing auth (AST) and hardcoded
    secrets (regex) — with ``file`` reported relative to ``root``.
    """
    root = Path(root)
    violations: list[dict] = []
    for path in find_python_files(root, exclude_globs):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        tree = _parse_ast(path)
        if tree is not None:
            violations.extend(check_sql_concatenation(root, path, tree, lines))
            violations.extend(check_missing_auth(root, path, tree, lines))
        violations.extend(check_hardcoded_secrets(root, path, lines))
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
