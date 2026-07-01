"""python-pytest detector for coder.logging.structured (+ coder.logging.print).

Realizes the agnostic obligation `coder.logging.structured` (disposition
`suppress-and-clean`) for the Python stack: production logging calls must carry
structured context via `extra={...}`. It ALSO emits `coder.logging.print` sites,
so ONE run carries TWO distinct rule_ids — exercising the v1.1 multi-rule output
channel (PROVIDER-CONTRACT-v1.1.md §3) exactly as the core dual-rule validator
file did.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_structured_logging.py
        :: detect_print_calls / detect_bare_log_calls / _is_excluded / _collect_files
    (origin/main, blob 112cb0d5f4234487). The AST detection logic is copied in
    spirit; the four ``atdd.coach.*`` substrate couplings were REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_PRINT`` / ``RULE_STRUCTURED``
    constants. Authoritative metadata (severity 2; print=strict,
    structured=suppress-and-clean) lives in the convention nodes, not bound at
    import. The detector only needs the ids.
  * ``Violation``  -> plain dicts in the v1.1 violation-output shape
    ``{rule_id, file, line, col, evidence, source_line}`` (PROVIDER-CONTRACT-v1.1
    §3.2). ``source_line`` carries the RAW offending line so the downstream
    consumer can apply suppress-and-clean disposition without re-reading files.
  * ``find_repo_root``  -> REMOVED. Scan scope is supplied explicitly via
    ``ATDD_SCAN_ROOTS`` / ``ATDD_SCAN_EXCLUDES`` (§2); never auto-discovered.
  * ``assert_disposition_satisfied``  -> NOT PORTED. This detector emits RAW
    violations only — INCLUDING bare calls that DO carry a suppress marker. It
    never decides suppression. That decision is the consumer's (§1). This is the
    crux of the Phase-0.5 re-proof: a non-strict rule whose verdict is computed
    entirely downstream.

Pure stdlib (``ast``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import ast
import fnmatch
from pathlib import Path

# The convention rule_ids this detector realizes.
RULE_PRINT = "coder.logging.print"            # disposition: strict   (sibling)
RULE_STRUCTURED = "coder.logging.structured"  # disposition: suppress-and-clean

# Logger method names that require extra= for structured context.
LOG_METHODS = frozenset(
    {"debug", "info", "warning", "error", "critical", "exception", "log"}
)
# Receiver names that indicate a logging call (not st.info, etc.).
LOGGER_RECEIVER_NAMES = frozenset({"logger", "log", "_logger", "_log", "logging", "LOG"})


def detect_print_calls(source: str, *, filename: str = "<unknown>") -> list[tuple[int, int]]:
    """Return (lineno, col) for each builtin ``print(...)`` call in ``source``."""
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError):
        return []
    hits: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            hits.append((node.lineno, node.col_offset))
    return hits


def detect_bare_log_calls(source: str, *, filename: str = "<unknown>") -> list[tuple[int, int, str]]:
    """Return (lineno, col, method) for logger.X() calls lacking an ``extra=`` kwarg.

    Matches an attribute call whose method is a standard logging level AND whose
    receiver is a known logger name, with no ``extra=`` keyword argument. Mirrors
    core ``detect_bare_log_calls``.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError):
        return []
    hits: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in LOG_METHODS):
            continue
        receiver = func.value
        if isinstance(receiver, ast.Name) and receiver.id in LOGGER_RECEIVER_NAMES:
            if not any(kw.arg == "extra" for kw in node.keywords):
                hits.append((node.lineno, node.col_offset, func.attr))
    return hits


def is_excluded(py_file: Path) -> bool:
    """True when ``py_file`` is out of scope (test code, caches, package shims)."""
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
    """True when ``rel`` (relative to its scan root) matches any exclusion glob."""
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def _collect_files(scan_root: Path, exclude_globs: list[str]) -> list[Path]:
    """In-scope ``*.py`` production files under ``scan_root`` (recursive)."""
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
    """Raw text of 1-based ``lineno`` (without trailing newline), or ''."""
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one ``root`` and return RAW v1.1 violation dicts (both rule_ids).

    Each violation is ``{rule_id, file, line, col, evidence, source_line}``.
    ``file`` is relative to ``root``. ``source_line`` is the RAW offending line —
    the detector NEVER inspects it for suppress markers; that is the consumer's
    disposition decision.
    """
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

        for lineno, col in detect_print_calls(source, filename=str(py_file)):
            violations.append(
                {
                    "rule_id": RULE_PRINT,
                    "file": str(rel),
                    "line": lineno,
                    "col": col,
                    "evidence": "print() call in production code (use a structured logger)",
                    "source_line": _line_text(lines, lineno),
                }
            )
        for lineno, col, method in detect_bare_log_calls(source, filename=str(py_file)):
            violations.append(
                {
                    "rule_id": RULE_STRUCTURED,
                    "file": str(rel),
                    "line": lineno,
                    "col": col,
                    "evidence": f"logger.{method}() without extra= keyword argument",
                    "source_line": _line_text(lines, lineno),
                }
            )
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan every root and return the concatenated RAW violation list."""
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
