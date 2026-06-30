"""python-pytest detector for coder.duplication.no-intra-layer-code-python.

Realizes the agnostic obligation `coder.duplication.no-intra-layer-code-python`
(disposition `strict`) for the Python stack: no structurally identical code
fragment may be duplicated across DIFFERENT files of the SAME architectural
layer. Detection is AST-subtree hashing over a sliding window of statements,
with names and literals normalized so renamed copies still collide.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_duplication_detector.py
        :: determine_layer_from_path / _ASTNormalizer / _hash_statements /
           strip_module_header / extract_fragments / find_intra_layer_duplicates
    (read-only core). The AST detection logic is copied in spirit; the four
    ``atdd.coach.*`` substrate couplings were REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_DUP_PY`` constant. Authoritative
    metadata (severity 2; disposition strict) lives in the convention node, not
    bound at import.
  * ``Violation``  -> plain dicts in the v1.1 violation-output shape
    ``{rule_id, file, line, col, evidence, source_line}`` (PROVIDER-CONTRACT-v1.1
    §3.2). ``source_line`` carries the RAW offending line (the first site of the
    duplicate pair).
  * ``find_repo_root`` + ``walk_consumer_python_files`` + convention YAML load
    -> REMOVED. Scan scope is supplied explicitly via ``ATDD_SCAN_ROOTS`` /
    ``ATDD_SCAN_EXCLUDES`` (§2); never auto-discovered. ``min_statements`` and the
    layer set are module constants matching the core convention defaults.
  * ``assert_disposition_satisfied``  -> NOT PORTED. This detector emits RAW
    violations only; the strict pass/fail verdict is the downstream consumer's
    (§1).

Files of multiple roots are pooled and grouped by layer BEFORE comparison, so a
multi-root consumer (`python/` + `src/atdd/`) detects a fragment duplicated
across roots within one layer — matching core, which scanned all scan_dirs into a
single by-layer map.

Pure stdlib (``ast``, ``hashlib``, ``fnmatch``, ``pathlib``) — no core imports.
"""
from __future__ import annotations

import ast
import fnmatch
import hashlib
from pathlib import Path

# The convention rule_id this detector realizes.
RULE_DUP_PY = "coder.duplication.no-intra-layer-code-python"  # disposition: strict

# Minimum AST statements in a fragment (core convention default).
MIN_STATEMENTS = 5

# Architectural layers compared (files outside these classify as 'unknown').
LAYERS = ("domain", "application", "presentation", "integration")

# Directory names skipped during the walk (vendored / build / cache).
_SKIP_DIRS = frozenset(
    {".git", "node_modules", "dist", "build", ".next", ".nuxt", "coverage",
     "__pycache__", ".cache", ".venv", "venv", "env", ".tox", ".mypy_cache",
     ".pytest_cache"}
)


def determine_layer_from_path(file_path: Path) -> str:
    """Determine the architectural layer of ``file_path`` (core-faithful)."""
    path_str = str(file_path).lower()

    if "/domain/" in path_str or path_str.endswith("/domain.py"):
        return "domain"
    elif "/application/" in path_str or path_str.endswith("/application.py"):
        return "application"
    elif "/presentation/" in path_str or path_str.endswith("/presentation.py"):
        return "presentation"
    elif "/integration/" in path_str or "/infrastructure/" in path_str:
        return "integration"

    if "/entities/" in path_str or "/models/" in path_str or "/value_objects/" in path_str:
        return "domain"
    elif "/use_cases/" in path_str or "/usecases/" in path_str or "/services/" in path_str:
        return "application"
    elif "/controllers/" in path_str or "/handlers/" in path_str or "/views/" in path_str:
        return "presentation"
    elif "/adapters/" in path_str or "/repositories/" in path_str or "/gateways/" in path_str:
        return "integration"

    return "unknown"


class _ASTNormalizer(ast.NodeTransformer):
    """Strip variable names and literal values from AST to capture structure only."""

    def visit_Name(self, node: ast.Name) -> ast.Name:
        self.generic_visit(node)
        return ast.copy_location(ast.Name(id="VAR", ctx=node.ctx), node)

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(value=""), node)
        if isinstance(node.value, (int, float, complex)):
            return ast.copy_location(ast.Constant(value=0), node)
        return node


def _hash_statements(stmts: list[ast.stmt]) -> str:
    """Normalize a list of statements and return a deterministic hash."""
    normalizer = _ASTNormalizer()
    normalized = []
    for stmt in stmts:
        normalized.append(normalizer.visit(ast.parse(ast.unparse(stmt)).body[0]))
    dumped = "\n".join(ast.dump(s) for s in normalized)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:16]


def _is_module_docstring(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _is_import(stmt: ast.stmt) -> bool:
    return isinstance(stmt, (ast.Import, ast.ImportFrom))


def _is_module_constant(stmt: ast.stmt) -> bool:
    return isinstance(stmt, (ast.Assign, ast.AnnAssign))


def strip_module_header(body: list[ast.stmt]) -> list[ast.stmt]:
    """Drop the contiguous leading header-boilerplate prefix (issue #960).

    Strips the leading docstring followed by a contiguous run of imports and
    module-level constant bindings, stopping at the first statement of real logic.
    Header statements that follow real code are NOT stripped.
    """
    idx = 0
    n = len(body)
    if idx < n and _is_module_docstring(body[idx]):
        idx += 1
    while idx < n and (_is_import(body[idx]) or _is_module_constant(body[idx])):
        idx += 1
    return body[idx:]


def extract_fragments(file_path: Path, min_statements: int) -> list[tuple[str, int, int]]:
    """Extract hashable code fragments — (hash, start_line, end_line)."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    fragments: list[tuple[str, int, int]] = []

    def _scan_body(body: list[ast.stmt]) -> None:
        if len(body) < min_statements:
            return
        for i in range(len(body) - min_statements + 1):
            window = body[i:i + min_statements]
            try:
                h = _hash_statements(window)
            except Exception:
                continue
            start_line = window[0].lineno
            end_line = window[-1].end_lineno or window[-1].lineno
            fragments.append((h, start_line, end_line))

    # Module-level statements, minus standard header boilerplate (#960).
    _scan_body(strip_module_header(tree.body))
    # Function/method bodies.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _scan_body(node.body)

    return fragments


def find_intra_layer_duplicates(
    files_by_layer: dict[str, list[Path]], min_statements: int
) -> list[dict]:
    """Find duplicate fragments within the same layer, across DIFFERENT files."""
    violations: list[dict] = []

    for layer, files in files_by_layer.items():
        if len(files) < 2:
            continue

        hash_map: dict[str, list[tuple[Path, int, int]]] = {}
        for f in files:
            for h, start, end in extract_fragments(f, min_statements):
                hash_map.setdefault(h, []).append((f, start, end))

        for h, locations in hash_map.items():
            unique_files = set(loc[0] for loc in locations)
            if len(unique_files) < 2:
                continue
            first = locations[0]
            for other in locations[1:]:
                if other[0] == first[0]:
                    continue
                violations.append({
                    "layer": layer,
                    "file_a": first[0],
                    "line_a": first[1],
                    "file_b": other[0],
                    "line_b": other[1],
                    "statements": min_statements,
                })

    return violations


def is_excluded(py_file: Path) -> bool:
    """True when ``py_file`` is out of scope (test code, package shims, caches)."""
    path_str = str(py_file)
    if "/tests/" in path_str or "/test/" in path_str:
        return True
    if py_file.name.startswith("test_"):
        return True
    if py_file.name == "conftest.py":
        return True
    if py_file.name == "__init__.py":
        return True
    if "__pycache__" in path_str:
        return True
    return False


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def _collect_files(scan_root: Path, exclude_globs: list[str]) -> list[tuple[Path, Path]]:
    """In-scope ``*.py`` files under ``scan_root`` as (absolute, relative) pairs."""
    if not scan_root.exists():
        return []
    out: list[tuple[Path, Path]] = []
    for p in sorted(scan_root.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if is_excluded(p):
            continue
        try:
            rel = p.relative_to(scan_root)
        except ValueError:
            rel = p
        if exclude_globs and _matches_exclude(rel, exclude_globs):
            continue
        out.append((p, rel))
    return out


def _line_text(path: Path, lineno: int) -> str:
    """RAW text of 1-based ``lineno`` in ``path`` (without trailing newline), or ''."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan every root, pool files by layer, return RAW v1.1 violation dicts.

    Each violation is ``{rule_id, file, line, col, evidence, source_line}``.
    ``file`` is the duplicate's first site, relative to its scan root. Files from
    all roots are grouped by layer together (core-faithful), so a fragment
    duplicated across roots within one layer is detected.
    """
    exclude_globs = exclude_globs or []
    # Map absolute path -> path relative to its own scan root (for reporting).
    rel_of: dict[Path, Path] = {}
    files_by_layer: dict[str, list[Path]] = {}
    for r in roots:
        for abs_p, rel_p in _collect_files(Path(r), exclude_globs):
            layer = determine_layer_from_path(abs_p)
            if layer == "unknown":
                continue
            rel_of[abs_p] = rel_p
            files_by_layer.setdefault(layer, []).append(abs_p)

    violations: list[dict] = []
    for v in find_intra_layer_duplicates(files_by_layer, MIN_STATEMENTS):
        rel_a = rel_of.get(v["file_a"], v["file_a"])
        rel_b = rel_of.get(v["file_b"], v["file_b"])
        violations.append({
            "rule_id": RULE_DUP_PY,
            "file": str(rel_a),
            "line": v["line_a"],
            "col": 0,
            "evidence": (
                f"[{v['layer']}] {rel_a}:{v['line_a']} <-> {rel_b}:{v['line_b']} "
                f"({v['statements']} identical statements)"
            ),
            "source_line": _line_text(v["file_a"], v["line_a"]),
        })
    return violations
