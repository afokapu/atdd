"""python-pytest detector for coder.error-response.bare-string (+ .code-format).

Realizes TWO sibling obligations of the error-response convention for the Python
stack, both disposition `strict`:
  * coder.error-response.bare-string  — HTTPException detail must be a structured
    dict, not a bare string / f-string.
  * coder.error-response.code-format  — `"error_code": "<value>"` must be
    UPPER_SNAKE_CASE (`^[A-Z][A-Z0-9_]+$`).
ONE run carries BOTH rule_ids — exercising the v1.1 multi-rule output channel
(PROVIDER-CONTRACT-v1.1.md §3) exactly as the core validator file did.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_error_response_compliance.py
        :: BARE_STRING_DETAIL_RE / ERROR_CODE_VALUE_RE / UPPER_SNAKE_CASE_RE /
           scan_bare_string_errors / scan_error_code_format
    (read-only core). The regex detection is copied verbatim; the
    ``atdd.coach.*`` substrate couplings + contract/convention meta-tests were
    REMOVED (those meta-tests gate the spec artifacts, not consumer source — they
    are not rule emitters and are out of scope for the detector).

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_BARE_STRING`` / ``RULE_CODE_FORMAT``
    constants. Authoritative metadata (severity 4; both strict) lives in the
    convention nodes.
  * ``Violation``  -> plain dicts in the v1.1 violation-output shape
    ``{rule_id, file, line, col, evidence, source_line}`` (§3.2).
  * ``find_repo_root`` + ``python/`` hard-code  -> REMOVED. Scan scope is supplied
    explicitly via ``ATDD_SCAN_ROOTS`` / ``ATDD_SCAN_EXCLUDES`` (§2).
  * ``assert_disposition_satisfied``  -> NOT PORTED. RAW emission only; the strict
    verdict is the downstream consumer's (§1).

Pure stdlib (``re``, ``fnmatch``, ``pathlib``) — no core imports.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

# The convention rule_ids this detector realizes.
RULE_BARE_STRING = "coder.error-response.bare-string"  # disposition: strict
RULE_CODE_FORMAT = "coder.error-response.code-format"   # disposition: strict

# Matches detail='...' / detail="..." / detail=f"..." (bare string) in an
# HTTPException call — copied verbatim from core.
BARE_STRING_DETAIL_RE = re.compile(
    r"""HTTPException\s*\([^)]*detail\s*=\s*(?:f?['"][^'"]*['"])""",
    re.DOTALL,
)

# Matches "error_code": "<value>" literals — copied verbatim from core.
ERROR_CODE_VALUE_RE = re.compile(
    r"""['\"]error_code['\"]\s*:\s*['\"]([^'"]+)['\"]""",
)

UPPER_SNAKE_CASE_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")

_SKIP_DIRS = frozenset({"__pycache__", ".git", "node_modules", ".venv", "venv"})


def is_excluded(py_file: Path) -> bool:
    """True when ``py_file`` is out of scope (bytecode caches / vendored dirs)."""
    return any(part in _SKIP_DIRS for part in py_file.parts)


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def _collect_files(scan_root: Path, exclude_globs: list[str]) -> list[tuple[Path, Path]]:
    """In-scope ``*.py`` files under ``scan_root`` as (absolute, relative) pairs."""
    if not scan_root.exists():
        return []
    out: list[tuple[Path, Path]] = []
    for p in sorted(scan_root.rglob("*.py")):
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


def _line_of(content: str, char_index: int) -> int:
    """1-based line number of ``char_index`` within ``content``."""
    return content[:char_index].count("\n") + 1


def _line_text(content: str, lineno: int) -> str:
    lines = content.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


def detect_bare_string_details(content: str) -> list[tuple[int, str]]:
    """Return (lineno, source_line) for each bare-string HTTPException detail."""
    hits: list[tuple[int, str]] = []
    if "HTTPException" not in content:
        return hits
    for m in BARE_STRING_DETAIL_RE.finditer(content):
        lineno = _line_of(content, m.start())
        hits.append((lineno, _line_text(content, lineno)))
    return hits


def detect_bad_error_codes(content: str) -> list[tuple[int, str, str]]:
    """Return (lineno, error_code, source_line) for non-UPPER_SNAKE_CASE codes."""
    hits: list[tuple[int, str, str]] = []
    for m in ERROR_CODE_VALUE_RE.finditer(content):
        error_code = m.group(1)
        if not UPPER_SNAKE_CASE_RE.match(error_code):
            lineno = _line_of(content, m.start())
            hits.append((lineno, error_code, _line_text(content, lineno)))
    return hits


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one root, return RAW v1.1 violation dicts (BOTH rule_ids)."""
    exclude_globs = exclude_globs or []
    violations: list[dict] = []
    for abs_p, rel_p in _collect_files(Path(root), exclude_globs):
        try:
            content = abs_p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for lineno, source_line in detect_bare_string_details(content):
            violations.append({
                "rule_id": RULE_BARE_STRING,
                "file": str(rel_p),
                "line": lineno,
                "col": 0,
                "evidence": "bare string detail in HTTPException (use a structured dict)",
                "source_line": source_line,
            })
        for lineno, error_code, source_line in detect_bad_error_codes(content):
            violations.append({
                "rule_id": RULE_CODE_FORMAT,
                "file": str(rel_p),
                "line": lineno,
                "col": 0,
                "evidence": f"error_code '{error_code}' is not UPPER_SNAKE_CASE",
                "source_line": source_line,
            })
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan every root and return the concatenated RAW violation list."""
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
