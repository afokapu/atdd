"""python-pytest detector for coder.refactor.complexity-* (FIVE rule_ids).

Realizes the agnostic REFACTOR-phase complexity obligations for the PYTHON stack.
ONE detector run carries FIVE distinct rule_ids (the v1.1 multi-rule output
channel, PROVIDER-CONTRACT-v1.1.md §3) — exactly the dual/multi binding the core
validator performs:

  * coder.refactor.complexity-cyclomatic — function cyclomatic complexity > 10
  * coder.refactor.complexity-nesting    — function nesting depth > 4
  * coder.refactor.complexity-length     — function length (LOC) > 50
  * coder.refactor.complexity-params     — function parameter count > 6
  * coder.refactor.complexity-cognitive  — function cognitive complexity > 15

All five are disposition `strict`; the strict aggregation is the downstream
consumer's job (§1). The detector emits RAW factual violations only.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_complexity.py
        :: find_python_files / extract_functions / calculate_cyclomatic_complexity
           / calculate_nesting_depth / count_function_lines
           / count_function_parameters / calculate_cognitive_complexity
           / _function_cognitive_complexity / scan_cyclomatic_complexity
           / scan_nesting_depth / scan_function_length / scan_function_params
           / scan_cognitive_complexity
    (origin/main, refactor.convention.yaml blob 3c4ee089cff5ec9e). The
    metric/AST/regex logic is copied behavior-for-behavior; the ``atdd.coach.*``
    substrate couplings were REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_*`` constants. Authoritative
    metadata (severities 2/3; all five strict) lives in the convention nodes, not
    bound at import.
  * ``Violation``  -> plain dicts in the v1.1 shape
    ``{rule_id, file, line, col, evidence, source_line}`` (§3.2). The core
    ``location = rel_path:line`` + ``detail`` (metric=value) are preserved inside
    ``file`` (scan-root-relative path), ``line`` and ``evidence``. Core never
    tracked a column, so ``col`` is 0 (consistent with the Wave-1 detectors).
  * ``find_repo_root`` + fixed ``REPO_ROOT / "python"`` root  -> REMOVED. Scan
    scope is supplied explicitly via ``ATDD_SCAN_ROOTS`` / ``ATDD_SCAN_EXCLUDES``
    (§2); never auto-discovered. Each ``ATDD_SCAN_ROOTS`` entry IS a python stack
    root and is scanned directly (the consumer ``python/`` case), exactly as core
    scanned ``REPO_ROOT / "python"``. The same test/__pycache__/__init__.py
    exclusions are preserved verbatim.
  * ``assert_disposition_satisfied`` (ratchet baseline)  -> NOT PORTED. All five
    rule_ids are strict, aggregated downstream by the consumer (§1). The ratchet
    baseline is consumer scan-policy, not detector logic.

Pure stdlib (``ast``, ``re``, ``fnmatch``, ``pathlib``) — no third-party or core
imports.
"""
from __future__ import annotations

import ast
import fnmatch
import re
from pathlib import Path
from typing import List, Tuple

# The convention rule_ids this detector realizes (all disposition: strict).
RULE_CYCLO = "coder.refactor.complexity-cyclomatic"   # cyclomatic complexity > 10
RULE_NEST = "coder.refactor.complexity-nesting"       # nesting depth > 4
RULE_LEN = "coder.refactor.complexity-length"         # function length (LOC) > 50
RULE_PARAMS = "coder.refactor.complexity-params"      # parameter count > 6
RULE_COGNITIVE = "coder.refactor.complexity-cognitive"  # cognitive complexity > 15

# Thresholds — copied verbatim from core test_complexity.py.
MAX_CYCLOMATIC_COMPLEXITY = 10
MAX_NESTING_DEPTH = 4
MAX_FUNCTION_LINES = 50
MAX_FUNCTION_PARAMS = 6
MAX_COGNITIVE_COMPLEXITY = 15


# ── file discovery (ported; rooted at the supplied scan root) ──────────────────


def collect_python_files(root: Path, exclude_globs: list[str] | None = None) -> List[Path]:
    """Find Python source files under ``root`` (excluding tests), core's filters.

    Mirrors core ``find_python_files`` / ``_collect_python_source_files`` exactly,
    except the root is the supplied scan root (not ``REPO_ROOT / "python"``) and an
    optional ``exclude_globs`` (relative-path fnmatch) is honored (§2).
    """
    if not root.exists():
        return []
    exclude_globs = exclude_globs or []
    files: List[Path] = []
    for py_file in sorted(root.rglob("*.py")):
        if "/test/" in str(py_file) or py_file.name.startswith("test_"):
            continue
        if "__pycache__" in str(py_file) or py_file.name == "__init__.py":
            continue
        if not py_file.is_file():
            continue
        if exclude_globs:
            try:
                rel = py_file.relative_to(root)
            except ValueError:
                rel = py_file
            if any(fnmatch.fnmatch(str(rel), pat) for pat in exclude_globs):
                continue
        files.append(py_file)
    return files


# ── function extraction + metrics (ported behavior-for-behavior from core) ─────


def extract_functions(file_path: Path) -> List[Tuple[str, int, str]]:
    """Extract (function_name, 1-based line, function_body) tuples. Ported verbatim."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []

    functions: List[Tuple[str, int, str]] = []
    lines = content.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i]
        func_match = re.match(r"^\s*(async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", line)
        if func_match:
            func_name = func_match.group(2)
            start_line = i + 1
            indent = len(line) - len(line.lstrip())

            body_lines = [line]
            i += 1
            while i < len(lines):
                current_line = lines[i]
                if not current_line.strip() or current_line.strip().startswith("#"):
                    body_lines.append(current_line)
                    i += 1
                    continue
                current_indent = len(current_line) - len(current_line.lstrip())
                if current_indent <= indent and current_line.strip():
                    break
                body_lines.append(current_line)
                i += 1

            function_body = "\n".join(body_lines)
            functions.append((func_name, start_line, function_body))
        else:
            i += 1

    return functions


def calculate_cyclomatic_complexity(function_body: str) -> int:
    """Cyclomatic complexity = decision points + 1. Ported verbatim."""
    complexity = 1
    keywords = ["if", "elif", "for", "while", "except", "case"]
    for keyword in keywords:
        pattern = r"\b" + keyword + r"\b"
        complexity += len(re.findall(pattern, function_body))

    condition_lines = [line for line in function_body.split("\n")
                       if re.search(r"\b(if|elif|while)\b", line)]
    for line in condition_lines:
        complexity += len(re.findall(r"\band\b", line))
        complexity += len(re.findall(r"\bor\b", line))
    return complexity


def calculate_nesting_depth(function_body: str) -> int:
    """Maximum nesting depth in a function. Ported verbatim."""
    max_depth = 0
    current_depth = 0
    base_indent = None

    for line in function_body.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if base_indent is None:
            base_indent = indent
            continue
        relative_indent = indent - base_indent
        current_depth = relative_indent // 4
        if stripped.endswith(":") and any(
            stripped.startswith(kw) for kw in
            ["if", "elif", "else", "for", "while", "with", "try", "except", "finally", "def", "class"]
        ):
            max_depth = max(max_depth, current_depth + 1)
        else:
            max_depth = max(max_depth, current_depth)
    return max_depth


def count_function_lines(function_body: str) -> int:
    """Count lines of code (excluding blank/comment lines). Ported verbatim."""
    lines = function_body.split("\n")
    code_lines = 0
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            code_lines += 1
    return code_lines


def count_function_parameters(function_body: str) -> int:
    """Count parameters (excluding self/cls). Ported verbatim."""
    first_line = function_body.split("\n")[0]
    match = re.search(r"def\s+\w+\s*\((.*?)\)", first_line)
    if not match:
        return 0
    params = match.group(1).strip()
    if not params:
        return 0
    param_list = [p.strip() for p in params.split(",")]
    param_list = [p for p in param_list if not p.startswith("self") and not p.startswith("cls")]
    return len(param_list)


def calculate_cognitive_complexity(source: str) -> List[Tuple[str, int, int]]:
    """Cognitive complexity per function (SonarQube algorithm). Ported verbatim."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    results: List[Tuple[str, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cc = _function_cognitive_complexity(node)
            results.append((node.name, node.lineno, cc))
    return results


def _function_cognitive_complexity(func_node: ast.AST) -> int:
    """Cognitive complexity for a single function AST node. Ported verbatim."""
    state = {"complexity": 0}

    def _walk_expr(expr: ast.AST) -> None:
        if isinstance(expr, ast.BoolOp):
            state["complexity"] += 1
        for child in ast.iter_child_nodes(expr):
            _walk_expr(child)

    def _walk_stmts(stmts, nesting: int) -> None:
        for stmt in stmts:
            _walk(stmt, nesting)

    def _handle_if_chain(node: ast.If, nesting: int) -> None:
        state["complexity"] += 1 + nesting
        _walk_expr(node.test)
        _walk_stmts(node.body, nesting + 1)
        orelse = node.orelse
        while orelse:
            if len(orelse) == 1 and isinstance(orelse[0], ast.If):
                elif_node = orelse[0]
                state["complexity"] += 1
                _walk_expr(elif_node.test)
                _walk_stmts(elif_node.body, nesting + 1)
                orelse = elif_node.orelse
            else:
                state["complexity"] += 1
                _walk_stmts(orelse, nesting + 1)
                orelse = None

    def _walk(node: ast.AST, nesting: int) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.If):
            _handle_if_chain(node, nesting)
            return
        if isinstance(node, (ast.For, ast.AsyncFor)):
            state["complexity"] += 1 + nesting
            _walk_expr(node.iter)
            _walk_stmts(node.body, nesting + 1)
            if node.orelse:
                state["complexity"] += 1
                _walk_stmts(node.orelse, nesting + 1)
            return
        if isinstance(node, ast.While):
            state["complexity"] += 1 + nesting
            _walk_expr(node.test)
            _walk_stmts(node.body, nesting + 1)
            if node.orelse:
                state["complexity"] += 1
                _walk_stmts(node.orelse, nesting + 1)
            return
        if isinstance(node, ast.Try):
            _walk_stmts(node.body, nesting)
            for handler in node.handlers:
                state["complexity"] += 1 + nesting
                _walk_stmts(handler.body, nesting + 1)
            if node.orelse:
                _walk_stmts(node.orelse, nesting)
            if node.finalbody:
                _walk_stmts(node.finalbody, nesting)
            return
        if hasattr(ast, "TryStar") and isinstance(node, ast.TryStar):
            _walk_stmts(node.body, nesting)
            for handler in node.handlers:
                state["complexity"] += 1 + nesting
                _walk_stmts(handler.body, nesting + 1)
            if node.orelse:
                _walk_stmts(node.orelse, nesting)
            if node.finalbody:
                _walk_stmts(node.finalbody, nesting)
            return
        if isinstance(node, (ast.With, ast.AsyncWith)):
            state["complexity"] += 1 + nesting
            _walk_stmts(node.body, nesting + 1)
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                _walk(child, nesting)
            elif isinstance(child, ast.expr):
                _walk_expr(child)

    _walk_stmts(func_node.body, 0)
    return state["complexity"]


# ── violation emitters (emit RAW v1.1 dicts) ──────────────────────────────────


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _body_first_line(function_body: str) -> str:
    """RAW text of the def line — body_lines[0] preserves original indentation."""
    return function_body.split("\n")[0]


def _source_line_at(source_lines: List[str], line: int) -> str:
    return source_lines[line - 1] if 1 <= line <= len(source_lines) else ""


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> List[dict]:
    """Scan one python stack ``root`` and return RAW v1.1 violation dicts.

    Runs all five metric scans per file and emits ``{rule_id,file,line,col,
    evidence,source_line}`` for every threshold breach. Discovery root == the
    supplied ``root`` (the consumer ``python/`` case). ``col`` is 0 (core tracked
    only ``rel_path:line``).
    """
    root = Path(root)
    violations: List[dict] = []
    for py_file in collect_python_files(root, exclude_globs):
        rel = _rel(root, py_file)
        try:
            source = py_file.read_text(encoding="utf-8")
        except Exception:
            source = ""
        source_lines = source.split("\n")
        functions = extract_functions(py_file)

        # cyclomatic — core skips functions with < 3 code lines.
        for func_name, line_num, func_body in functions:
            if count_function_lines(func_body) < 3:
                continue
            complexity = calculate_cyclomatic_complexity(func_body)
            if complexity > MAX_CYCLOMATIC_COMPLEXITY:
                violations.append({
                    "rule_id": RULE_CYCLO,
                    "file": rel,
                    "line": line_num,
                    "col": 0,
                    "evidence": f"{func_name} complexity={complexity} (>{MAX_CYCLOMATIC_COMPLEXITY})",
                    "source_line": _body_first_line(func_body),
                })

        # nesting depth
        for func_name, line_num, func_body in functions:
            depth = calculate_nesting_depth(func_body)
            if depth > MAX_NESTING_DEPTH:
                violations.append({
                    "rule_id": RULE_NEST,
                    "file": rel,
                    "line": line_num,
                    "col": 0,
                    "evidence": f"{func_name} depth={depth} (>{MAX_NESTING_DEPTH})",
                    "source_line": _body_first_line(func_body),
                })

        # function length
        for func_name, line_num, func_body in functions:
            lines = count_function_lines(func_body)
            if lines > MAX_FUNCTION_LINES:
                violations.append({
                    "rule_id": RULE_LEN,
                    "file": rel,
                    "line": line_num,
                    "col": 0,
                    "evidence": f"{func_name} lines={lines} (>{MAX_FUNCTION_LINES})",
                    "source_line": _body_first_line(func_body),
                })

        # parameter count
        for func_name, line_num, func_body in functions:
            param_count = count_function_parameters(func_body)
            if param_count > MAX_FUNCTION_PARAMS:
                violations.append({
                    "rule_id": RULE_PARAMS,
                    "file": rel,
                    "line": line_num,
                    "col": 0,
                    "evidence": f"{func_name} params={param_count} (>{MAX_FUNCTION_PARAMS})",
                    "source_line": _body_first_line(func_body),
                })

        # cognitive complexity (AST)
        for func_name, line_num, cc in calculate_cognitive_complexity(source):
            if cc > MAX_COGNITIVE_COMPLEXITY:
                violations.append({
                    "rule_id": RULE_COGNITIVE,
                    "file": rel,
                    "line": line_num,
                    "col": 0,
                    "evidence": f"{func_name} cognitive_complexity={cc} (>{MAX_COGNITIVE_COMPLEXITY})",
                    "source_line": _source_line_at(source_lines, line_num),
                })

    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> List[dict]:
    """Scan every root and return the concatenated RAW violation list."""
    out: List[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
