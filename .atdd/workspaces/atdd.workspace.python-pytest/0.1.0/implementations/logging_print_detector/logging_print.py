"""python-pytest detector for coder.logging.print.

Realizes the agnostic obligation `coder.logging.print` (atdd.extension.coder) for
the Python stack: production code must not emit diagnostics via the builtin
`print()` — it must use a structured logger.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_structured_logging.py
        :: detect_print_calls / _is_excluded / _collect_files
    (origin/main, blob 112cb0d5f4234487). The AST detection logic is copied
    verbatim in spirit; the four ``atdd.coach.*`` substrate couplings were
    REMOVED — see the workspace decoupling notes below.

DECOUPLED FROM CORE (every adaptation made, per Phase-0 task §3):
  * ``bind_rule("coder.logging.print")``  -> replaced by the module-level
    ``RULE_ID`` constant. The authoritative rule metadata (severity 2,
    disposition strict, alias LOGGING-PRINT-001) now lives in the convention
    node, not bound at validator import. The detector only needs the id.
  * ``atdd.coach.validators._violation.Violation``  -> replaced by a plain dict
    ``{"rule_id", "location", "evidence"}`` matching the python-pytest run
    contract's violation-output shape (adapter/run.py::_to_violations).
  * ``atdd.coach.utils.repo.find_repo_root``  -> removed. The detector scans an
    explicit caller-supplied path (the workspace instance / a fixture), never a
    globally-discovered consumer repo root.
  * ``atdd.coach.utils.disposition_gate.assert_disposition_satisfied``  ->
    removed. Pass/fail is the pytest assertion in test_logging_print.py; the
    disposition (strict) is declared by the convention node and applied by the
    coach layer, not by the detector. Suppression-marker handling is therefore
    NOT ported (see PHASE0-PROOF "GAPS / RISKS").

Pure stdlib (``ast``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import ast
import fnmatch
from pathlib import Path

# The convention rule_id this detector realizes. Kept == implementation_id so a
# failing pytest run surfaces a violation carrying this exact rule_id.
RULE_ID = "coder.logging.print"


def detect_print_calls(source: str, *, filename: str = "<unknown>") -> list[tuple[int, int]]:
    """Return (lineno, col) for each builtin ``print(...)`` call in ``source``.

    AST-based (``ast.Call`` whose ``func`` is the bare ``Name`` ``print``), so
    ``obj.print(...)`` methods and ``print`` referenced without a call do not
    match. Unparseable / non-UTF-8 source yields no findings — a syntax error is
    a different validator's concern, not this detector's.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError):
        return []
    hits: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            hits.append((node.lineno, node.col_offset))
    return hits


def is_excluded(py_file: Path) -> bool:
    """True when ``py_file`` is out of scope (test code, caches, package shims).

    Mirrors core ``_is_excluded``: test files and ``tests/`` dirs print freely,
    ``__pycache__`` is generated, and ``__init__.py`` is a re-export shim.
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
    """True when ``rel`` (relative to its scan base) matches any exclusion glob.

    Mirrors the structured_logging detector: ``ATDD_SCAN_EXCLUDES`` globs are
    fnmatch-ed against the path RELATIVE to the scan base, so a caller-supplied
    glob like ``*/generated/*`` drops generated trees the same way it does there.
    """
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def _collect_files(scan_dir: Path, exclude_globs: list[str] | None = None) -> list[Path]:
    """Collect in-scope ``*.py`` production files under ``scan_dir`` (recursive).

    Applies BOTH the hard-coded ``is_excluded`` filter (test code, caches, shims)
    AND any caller-supplied ``exclude_globs`` (``ATDD_SCAN_EXCLUDES``), the latter
    fnmatch-ed against each file's path relative to ``scan_dir``.
    """
    if not scan_dir.exists():
        return []
    exclude_globs = exclude_globs or []
    out: list[Path] = []
    for p in sorted(scan_dir.rglob("*.py")):
        if is_excluded(p):
            continue
        try:
            rel = p.relative_to(scan_dir)
        except ValueError:
            rel = p
        if exclude_globs and _matches_exclude(rel, exclude_globs):
            continue
        out.append(p)
    return out


def scan_path(target: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan ``target`` (a file or directory) and return violation dicts.

    Each violation is ``{"rule_id", "location", "evidence"}`` — the
    python-pytest run-contract violation shape. ``location`` is ``<relpath>:line:col``
    relative to ``target`` (or to its parent when ``target`` is a file).

    ``exclude_globs`` is the ``ATDD_SCAN_EXCLUDES`` exclusion-glob list (§2 of the
    provider contract). Previously this v1.0.0 detector SILENTLY IGNORED excludes
    (only structured_logging honored them) — wiring a rule whose detector drops
    excludes would be a correctness bug (PHASE0-PROOF GAP G2). Now honored, the
    same way structured_logging does: globs are fnmatch-ed against each file's
    path relative to the scan base.
    """
    target = Path(target)
    exclude_globs = exclude_globs or []
    if target.is_dir():
        files = _collect_files(target, exclude_globs)
        base = target
    else:
        excluded = is_excluded(target) or _matches_exclude(target.name, exclude_globs)
        files = [] if excluded else [target]
        base = target.parent

    violations: list[dict] = []
    for py_file in files:
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, col in detect_print_calls(source, filename=str(py_file)):
            try:
                rel = py_file.relative_to(base)
            except ValueError:
                rel = py_file
            violations.append(
                {
                    "rule_id": RULE_ID,
                    "location": f"{rel}:{lineno}:{col}",
                    "evidence": "print() call in production code (use a structured logger)",
                }
            )
    return violations
