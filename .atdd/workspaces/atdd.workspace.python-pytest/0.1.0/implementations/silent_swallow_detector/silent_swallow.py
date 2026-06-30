"""python-pytest detector for coder.logging.coach-silent-swallow.

Realizes the agnostic obligation ``coder.logging.coach-silent-swallow``
(disposition ``suppress-and-clean``, severity 4) for the Python stack: an
exception handler in production code must observably react (log or re-raise) and
must never silently swallow — i.e. ``except: pass`` or a handler that returns a
value with no log and no raise.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_no_silent_exception_swallowing_python.py
        :: detect_silent_swallows / _is_logger_call / _walk_handler_body /
           _handler_has_raise / _handler_explicit_returns / _handler_body_is_only_pass
    (origin/main, blob 9084a40d2e43e7d3). The AST detection is copied in spirit;
    the ``atdd.coach.*`` substrate couplings were REMOVED. Convention provenance:
    src/atdd/coder/conventions/logging.convention.yaml (blob b5999f8489b06e20),
    rule ``coder.logging.coach-silent-swallow`` (alias COACH-SILENT-SWALLOW-001).

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule("coder.logging.coach-silent-swallow")``  -> module-level
    ``RULE_SILENT_SWALLOW`` constant. Authoritative metadata (severity 4,
    disposition suppress-and-clean) lives in the convention node, not bound at
    import.
  * ``Violation``  -> plain dicts in the v1.1 violation-output shape
    ``{rule_id, file, line, col, evidence, source_line}`` (PROVIDER-CONTRACT-v1.1
    §3.2). ``source_line`` carries the RAW ``except`` line so the downstream
    consumer can apply suppress-and-clean disposition without re-reading files.
  * ``find_repo_root`` + dual-dir scan (python/ + src/atdd/ + web/src/)  ->
    REMOVED. Scan scope is supplied explicitly via ``ATDD_SCAN_ROOTS`` /
    ``ATDD_SCAN_EXCLUDES`` (§2); never auto-discovered.
  * ``_is_suppressed`` (the inline ``# atdd:suppress(...)`` marker check)  ->
    NOT PORTED into the detector. Like the structured-logging re-proof, this
    detector emits RAW violations INCLUDING handlers that carry a suppress
    marker; whether a marker absorbs a violation is the consumer's
    suppress-and-clean disposition decision (§1), never the detector's.

Pure stdlib (``ast``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import ast
import fnmatch
from pathlib import Path

# The convention rule_id this detector realizes.
RULE_SILENT_SWALLOW = "coder.logging.coach-silent-swallow"  # disposition: suppress-and-clean

# Receiver names + methods that mark an observable logging reaction (mirrors core).
LOGGER_RECEIVER_NAMES = frozenset({"logger", "log", "_logger", "_log", "logging", "LOG"})
LOG_METHODS = frozenset(
    {"debug", "info", "warning", "warn", "error", "critical", "exception", "log"}
)

# Scopes we never descend into when judging a handler body: a handler that only
# DEFINES a function/class/lambda which would log does not itself react.
_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _is_logger_call(node: ast.AST) -> bool:
    """``logger.warning(...)`` / ``self.logger.error(...)`` / ``logging.info(...)``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in LOG_METHODS:
        return False
    receiver = func.value
    if isinstance(receiver, ast.Name) and receiver.id in LOGGER_RECEIVER_NAMES:
        return True
    if isinstance(receiver, ast.Attribute) and receiver.attr in LOGGER_RECEIVER_NAMES:
        return True
    return False


def _walk_handler_body(handler: ast.ExceptHandler):
    """Iterate nodes inside the handler body, skipping nested scopes."""
    stack: list[ast.AST] = list(handler.body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, _NESTED_SCOPES):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _handler_has_log_call(handler: ast.ExceptHandler) -> bool:
    return any(_is_logger_call(n) for n in _walk_handler_body(handler))


def _handler_has_raise(handler: ast.ExceptHandler) -> bool:
    """True if a ``raise`` appears at any depth (excluding nested scopes)."""
    return any(isinstance(n, ast.Raise) for n in _walk_handler_body(handler))


def _handler_explicit_returns(handler: ast.ExceptHandler) -> list[ast.Return]:
    return [n for n in _walk_handler_body(handler) if isinstance(n, ast.Return)]


def _handler_body_is_only_pass(handler: ast.ExceptHandler) -> bool:
    """``except X: pass`` (single ``pass`` statement, no other side effects)."""
    return len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)


def _format_except_clause(node: ast.AST | None) -> str:
    """Render ``except SomeError`` / ``except (A, B)`` for the violation detail."""
    if node is None:
        return "bare except"
    try:
        return ast.unparse(node)
    except (AttributeError, ValueError):
        return "<unparsable>"


def detect_silent_swallows(source: str, *, filename: str = "<unknown>") -> list[tuple[int, int, str]]:
    """Return (lineno, col, evidence) for every silent-swallow handler in ``source``.

    A handler is a silent swallow when it has NO log call, NO raise, AND either is
    a single ``pass`` or contains an explicit ``return``. Mirrors core
    ``detect_silent_swallows`` minus the suppression-marker check (that is the
    consumer's suppress-and-clean disposition decision).
    """
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError):
        return []

    hits: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if _handler_has_log_call(handler):
                continue
            if _handler_has_raise(handler):
                continue

            returns = _handler_explicit_returns(handler)
            empty_pass = _handler_body_is_only_pass(handler)

            # A handler that does *something* (assignment, call) but does not
            # return and is not a bare pass is NOT flagged — matches core's
            # deliberate conservatism (the canonical incident shape is a return).
            if not returns and not empty_pass:
                continue

            exc_type = _format_except_clause(handler.type)
            if empty_pass and not returns:
                evidence = f"silent swallow ({exc_type}: pass) — no log, no raise"
            else:
                evidence = (
                    f"silent swallow ({exc_type}) — no log, no raise; "
                    f"returns from handler ({len(returns)} return statement(s))"
                )
            hits.append((handler.lineno, handler.col_offset, evidence))
    return hits


def is_excluded(py_file: Path) -> bool:
    """True when ``py_file`` is out of scope (tests, shims, caches).

    NOTE — core also excluded ``*/fixtures/*``; that is consumer SCAN-POLICY
    (don't scan the repo's own fixture trees), supplied via ``ATDD_SCAN_EXCLUDES``
    in the hermetic model, NOT detector logic. The fixtures this detector ships
    ARE the code-under-inspection, so the detector must not hardcode that carve.
    """
    path_str = str(py_file)
    if "/tests/" in path_str or "/test/" in path_str:
        return True
    if py_file.name.startswith("test_"):
        return True
    if py_file.name.endswith("_test.py"):
        return True
    if py_file.name == "conftest.py":
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
    """Scan one ``root`` and return RAW v1.1 violation dicts.

    Each violation is ``{rule_id, file, line, col, evidence, source_line}``;
    ``file`` is relative to ``root`` and ``source_line`` is the RAW ``except``
    line. The detector NEVER inspects ``source_line`` for suppress markers — that
    is the consumer's disposition decision.
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
        for lineno, col, evidence in detect_silent_swallows(source, filename=str(py_file)):
            violations.append(
                {
                    "rule_id": RULE_SILENT_SWALLOW,
                    "file": str(rel),
                    "line": lineno,
                    "col": col,
                    "evidence": evidence,
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
