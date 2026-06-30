"""python-pytest detector for coder.refactor.nplus1 (N+1 query pattern).

Realizes the agnostic obligation ``coder.refactor.nplus1`` (disposition
``strict``, severity 3): production code must not issue a database (or HTTP-as-DB)
client call inside a loop body or comprehension — the classic N+1 pattern.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_query_count.py
        :: find_python_files / _annotate_parents / _find_enclosing_function /
           _is_db_call / _get_loop_body_nodes / detect_n_plus_one
    (origin/main, blob 23c258936cd04042). AST detection copied in spirit; the
    ``atdd.coach.*`` substrate couplings were REMOVED. Convention provenance:
    src/atdd/coder/conventions/refactor.convention.yaml (blob 3c4ee089cff5ec9e),
    rule ``coder.refactor.nplus1`` (alias REFACTOR-NPLUS1-001).

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule("coder.refactor.nplus1")``  -> module-level ``RULE_NPLUS1``
    constant. Severity 3 / disposition strict live in the convention node.
  * ``Violation``  -> plain dicts ``{rule_id, file, line, col, evidence,
    source_line}`` (v1.1 §3.2). ``col`` is the call's ``col_offset``;
    ``source_line`` is the RAW call line.
  * ``find_repo_root`` / ``find_python_dir``  -> REMOVED. Scan scope is supplied
    explicitly via ``ATDD_SCAN_ROOTS`` / ``ATDD_SCAN_EXCLUDES`` (§2). Core's
    hardcoded ``/migrations/`` skip is now a consumer exclude-glob.
  * ratchet baseline  -> NOT PORTED (downstream consumer disposition concern).

DISPOSITION WRINKLE (documented honestly):
  Core honors an inline ``# noqa: N+1`` marker by DROPPING the call before it ever
  becomes a violation. That marker is NOT an ``atdd:suppress(<rule_id>)`` marker
  and this rule's disposition is ``strict`` (which, by definition, ignores
  ``atdd:suppress`` markers downstream). So ``# noqa: N+1`` cannot be re-homed to
  the consumer's suppress-and-clean path without changing the rule's disposition.
  To preserve core's pass/fail behavior, ``# noqa: N+1`` is kept as a DETECTION
  EXEMPTION inside the detector (like test-file/migration exclusions) — a
  noqa-marked call is simply not a violation. The RAW channel still carries
  ``source_line`` for every emitted violation. See PHASE05-PROOF §6.

Pure stdlib (``ast``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import ast
import fnmatch
from pathlib import Path

# The convention rule_id this detector realizes.
RULE_NPLUS1 = "coder.refactor.nplus1"  # disposition: strict

# DB client method names that indicate a database call when used as attribute calls.
DB_CALL_METHODS = frozenset(
    {
        # Repository / ORM pattern
        "execute", "executemany",
        "fetch", "fetchone", "fetchall", "fetchrow", "fetchval",
        "find", "find_one", "find_many",
        "insert", "insert_one", "insert_many",
        "update_one", "update_many",
        "delete_one", "delete_many",
        "upsert", "save", "aggregate",
        # Supabase chain starters
        "table", "from_", "rpc",
        # Direct DB cursor
        "cursor", "mogrify",
    }
)

# HTTP methods flagged only when called on known HTTP modules.
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "request", "send"})
HTTP_MODULES = frozenset({"requests", "httpx", "aiohttp"})

# Inline detection-exemption marker (NOT an atdd:suppress disposition marker).
SUPPRESSION_COMMENT = "noqa: N+1"

_LOOP_TYPES = (
    ast.For, ast.While, ast.AsyncFor,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
)


def _annotate_parents(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child._parent = node  # type: ignore[attr-defined]


def _find_enclosing_function(node: ast.AST) -> str | None:
    current = node
    while hasattr(current, "_parent"):
        current = current._parent  # type: ignore[attr-defined]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return None


def _is_db_call(node: ast.Call) -> str | None:
    """Human-readable description of a DB/HTTP-as-DB call, or None."""
    if isinstance(node.func, ast.Attribute):
        method_name = node.func.attr
        if method_name in DB_CALL_METHODS:
            return f".{method_name}()"
        if method_name in HTTP_METHODS and isinstance(node.func.value, ast.Name):
            if node.func.value.id in HTTP_MODULES:
                return f"{node.func.value.id}.{method_name}()"
    return None


def _get_loop_body_nodes(loop_node: ast.AST) -> list[ast.AST]:
    if isinstance(loop_node, (ast.For, ast.While, ast.AsyncFor)):
        return list(loop_node.body)
    if isinstance(loop_node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        return [loop_node.elt] + list(loop_node.generators)
    if isinstance(loop_node, ast.DictComp):
        return [loop_node.key, loop_node.value] + list(loop_node.generators)
    return []


def detect_n_plus_one(source: str, *, filename: str = "<unknown>") -> list[tuple[int, int, str]]:
    """Return (lineno, col, evidence) for each DB/HTTP call inside a loop/comprehension.

    A call carrying an inline ``# noqa: N+1`` marker on its line is exempt
    (detection-level, mirroring core — see module docstring).
    """
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError):
        return []

    _annotate_parents(tree)
    source_lines = source.splitlines()
    hits: list[tuple[int, int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, _LOOP_TYPES):
            continue
        for body_node in _get_loop_body_nodes(node):
            for child in ast.walk(body_node):
                if not isinstance(child, ast.Call):
                    continue
                desc = _is_db_call(child)
                if desc is None:
                    continue
                if not hasattr(child, "lineno"):
                    continue
                line_idx = child.lineno - 1
                if 0 <= line_idx < len(source_lines) and SUPPRESSION_COMMENT in source_lines[line_idx]:
                    continue  # detection-level exemption (noqa: N+1)
                func_name = _find_enclosing_function(child) or "<module>"
                loop_type = type(node).__name__
                evidence = f"{func_name} {desc} in {loop_type}"
                hits.append((child.lineno, child.col_offset, evidence))
    return hits


def is_excluded(py_file: Path) -> bool:
    """True when ``py_file`` is out of scope (tests, shims, caches).

    NOTE — core also skipped ``*/migrations/*``; that is consumer SCAN-POLICY,
    supplied via ``ATDD_SCAN_EXCLUDES`` in the hermetic model, not detector logic.
    """
    path_str = str(py_file)
    if "/tests/" in path_str or "/test/" in path_str:
        return True
    if py_file.name.startswith("test_"):
        return True
    if "__pycache__" in path_str:
        return True
    if py_file.name == "__init__.py":
        return True
    return False


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def _collect_files(scan_root: Path, exclude_globs: list[str]) -> list[Path]:
    if not scan_root.exists():
        return []
    out: list[Path] = []
    for p in sorted(scan_root.rglob("*.py")):
        if is_excluded(p):
            continue
        try:
            rel = p.relative_to(scan_root)
        except ValueError:
            rel = p
        if exclude_globs and _matches_exclude(rel, exclude_globs):
            continue
        out.append(p)
    return out


def _line_text(lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one ``root`` and return RAW v1.1 violation dicts."""
    root = Path(root)
    exclude_globs = exclude_globs or []
    violations: list[dict] = []
    for py_file in _collect_files(root, exclude_globs):
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = source.splitlines()
        try:
            rel = py_file.relative_to(root)
        except ValueError:
            rel = py_file
        for lineno, col, evidence in detect_n_plus_one(source, filename=str(py_file)):
            violations.append(
                {
                    "rule_id": RULE_NPLUS1,
                    "file": str(rel),
                    "line": lineno,
                    "col": col,
                    "evidence": evidence,
                    "source_line": _line_text(lines, lineno),
                }
            )
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
