"""python-pytest detector for coder.boundaries.http-client.

Realizes the agnostic boundary obligation `coder.boundaries.http-client`
(disposition `strict`) for the TypeScript/Preact stack: frontend production code
must route HTTP through the contract-driven HttpClient, not the raw `fetch()`
primitive. Detection is a line-wise regex over non-test `*.ts`/`*.tsx` source.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_contract_driven_http.py
        :: _RAW_FETCH_RE / _is_test_file / find_ts_files / scan_raw_fetch
    (read-only core). The regex detection is copied verbatim; the
    ``atdd.coach.*`` substrate couplings were REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_HTTP_CLIENT`` constant.
    Authoritative metadata (severity 3; strict) lives in the convention node.
  * ``Violation``  -> plain dicts in the v1.1 violation-output shape
    ``{rule_id, file, line, col, evidence, source_line}`` (§3.2).
  * ``find_repo_root`` + ``.atdd/config.yaml`` whitelist load  -> REMOVED. Scan
    scope is supplied explicitly via ``ATDD_SCAN_ROOTS``; the consumer's
    ``contract_driven_http.whitelist`` is transported IN as ``ATDD_SCAN_EXCLUDES``
    (§2) rather than read from disk.
  * ``assert_disposition_satisfied``  -> NOT PORTED. RAW emission only; the strict
    verdict is the downstream consumer's (§1).

Pure stdlib (``re``, ``fnmatch``, ``pathlib``) — no core imports.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

# The convention rule_id this detector realizes.
RULE_HTTP_CLIENT = "coder.boundaries.http-client"  # disposition: strict

# Matches `fetch(` / `fetch (` but not `obj.fetch(` or `prefetch(` — verbatim.
_RAW_FETCH_RE = re.compile(r"(?<![.\w])fetch\s*\(")

_TS_EXTENSIONS = (".ts", ".tsx")
_SKIP_DIRS = frozenset(
    {".git", "__pycache__", "node_modules", ".dart_tool", "build", ".pub-cache",
     "dist", ".next", ".nuxt", "coverage", ".venv", "venv", "env", ".tox",
     ".mypy_cache", ".pytest_cache"}
)


def is_test_file(path: Path) -> bool:
    """True when ``path`` is a test/spec file that should be skipped (core-faithful)."""
    name = path.name
    if name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
        return True
    if "__tests__" in path.parts:
        return True
    return False


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def _collect_files(scan_root: Path, exclude_globs: list[str]) -> list[tuple[Path, Path]]:
    """In-scope ``*.ts``/``*.tsx`` files as (absolute, relative) pairs.

    ``exclude_globs`` carries the consumer's whitelist transported as scan
    excludes (matched relative to the scan root, as core matched its whitelist).
    """
    if not scan_root.exists():
        return []
    out: list[tuple[Path, Path]] = []
    for p in sorted(scan_root.rglob("*")):
        if not p.is_file() or p.suffix not in _TS_EXTENSIONS:
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if is_test_file(p):
            continue
        try:
            rel = p.relative_to(scan_root)
        except ValueError:
            rel = p
        if exclude_globs and _matches_exclude(rel, exclude_globs):
            continue
        out.append((p, rel))
    return out


def detect_raw_fetch(content: str) -> list[tuple[int, str]]:
    """Return (lineno, source_line) for each raw fetch() call in ``content``.

    Single-line and block-comment lines are skipped, matching core.
    """
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        if _RAW_FETCH_RE.search(line):
            hits.append((lineno, line))
    return hits


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one root, return RAW v1.1 violation dicts for raw fetch() calls."""
    exclude_globs = exclude_globs or []
    violations: list[dict] = []
    for abs_p, rel_p in _collect_files(Path(root), exclude_globs):
        try:
            content = abs_p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, source_line in detect_raw_fetch(content):
            snippet = source_line.strip()
            snippet = snippet[:80] + ("..." if len(snippet) > 80 else "")
            violations.append({
                "rule_id": RULE_HTTP_CLIENT,
                "file": str(rel_p),
                "line": lineno,
                "col": 0,
                "evidence": f"raw fetch() call (use the contract-driven HttpClient): {snippet}",
                "source_line": source_line,
            })
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan every root and return the concatenated RAW violation list."""
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
