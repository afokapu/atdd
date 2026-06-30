"""python-pytest detector for coder.presentation.gsap-layer (+ .gsap-commons).

Realizes the agnostic obligation `coder.presentation.gsap-layer` (disposition
`strict`) for the web/TypeScript stack: GSAP (animation) imports are allowed
ONLY from a feature's `presentation/` layer. It ALSO emits
`coder.presentation.gsap-commons` (also strict) for any GSAP import found under
`web/src/commons/` — so ONE run carries TWO distinct rule_ids, exercising the
v1.1 multi-rule output channel (PROVIDER-CONTRACT-v1.1.md §3) exactly as the core
dual-binding validator does.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_gsap_layer_usage.py
        :: GSAP_IMPORT_PATTERNS / _is_presentation_layer / _find_gsap_import /
           _scan_files_for_gsap / scan_gsap_layer_usage / scan_gsap_commons
    (origin/main @ 624d3afe, blob 736430211d32eee3). The regex detection is copied
    verbatim; the four ``atdd.coach.*`` substrate couplings were REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_LAYER`` / ``RULE_COMMONS``
    constants. Authoritative metadata (severity 3; both strict) lives in the
    convention nodes, not bound at import.
  * ``Violation``  -> plain dicts in the v1.1 violation-output shape
    ``{rule_id, file, line, col, evidence, source_line}`` (§3.2). ``source_line``
    carries the RAW offending import line.
  * ``find_repo_root`` + fixed ``web/src`` root  -> REMOVED. Scan scope is
    supplied explicitly via ``ATDD_SCAN_ROOTS`` / ``ATDD_SCAN_EXCLUDES`` (§2);
    never auto-discovered. Each scan root is treated as a `web/src`-equivalent
    root: layer membership is read from its FIRST-RELATIVE path segments
    (``{wagon}/{feature}/{layer}/...``), exactly as core read them relative to
    ``WEB_SRC``.
  * ``assert_disposition_satisfied`` (ratchet baseline)  -> NOT PORTED. The
    detector emits RAW violations only; both rule_ids are `strict`, so the
    downstream consumer fails on any unsuppressed site. The ratchet baseline is
    consumer scan-policy, not detector logic (§1).

Pure stdlib (``re``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

# The convention rule_ids this detector realizes.
RULE_LAYER = "coder.presentation.gsap-layer"      # GSAP outside presentation/
RULE_COMMONS = "coder.presentation.gsap-commons"  # GSAP anywhere under commons/

# GSAP import detection patterns — copied verbatim from core (Section 6 of the
# GSAP Stack Integration Spec): ESM, type-only, dynamic import(), and CJS require.
GSAP_IMPORT_PATTERNS = [
    r'''import\s+.*?\s+from\s+["']gsap["']''',
    r'''import\s+.*?\s+from\s+["']gsap/[^"']+["']''',
    r'''import\s+.*?\s+from\s+["']@gsap/[^"']+["']''',
    r'''import\s+type\s+.*?\s+from\s+["']gsap["']''',
    r'''import\s+type\s+.*?\s+from\s+["']gsap/[^"']+["']''',
    r'''import\s+type\s+.*?\s+from\s+["']@gsap/[^"']+["']''',
    r'''import\s*\(\s*["']gsap["']\s*\)''',
    r'''import\s*\(\s*["']gsap/[^"']+["']\s*\)''',
    r'''import\s*\(\s*["']@gsap/[^"']+["']\s*\)''',
    r'''require\s*\(\s*["']gsap["']\s*\)''',
    r'''require\s*\(\s*["']gsap/[^"']+["']\s*\)''',
    r'''require\s*\(\s*["']@gsap/[^"']+["']\s*\)''',
]
GSAP_PATTERNS_COMPILED = [re.compile(p, re.MULTILINE) for p in GSAP_IMPORT_PATTERNS]

TS_SUFFIXES = (".ts", ".tsx")


def is_presentation_layer(rel_parts: tuple[str, ...]) -> bool:
    """True when ``rel_parts`` (path relative to a web/src root) is presentation.

    Mirrors core ``_is_presentation_layer``: ``{wagon}/{feature}/{layer}/...`` so
    the layer is segment index 2. ``commons/**`` is never presentation.
    """
    if rel_parts and rel_parts[0] == "commons":
        return False
    if len(rel_parts) >= 3:
        return rel_parts[2] == "presentation"
    return False


def find_gsap_import(content: str) -> tuple[str, int] | None:
    """Return (matched_import, 1-based line) of the first GSAP import, or None."""
    for pattern in GSAP_PATTERNS_COMPILED:
        match = pattern.search(content)
        if match:
            line = content.count("\n", 0, match.start()) + 1
            return match.group(0), line
    return None


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def _collect_ts_files(root: Path, exclude_globs: list[str]) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    for suffix in TS_SUFFIXES:
        for p in sorted(root.rglob(f"*{suffix}")):
            if not p.is_file():
                continue
            try:
                rel = p.relative_to(root)
            except ValueError:
                rel = p
            if exclude_globs and _matches_exclude(rel, exclude_globs):
                continue
            out.append(p)
    return sorted(set(out))


def _line_text(content: str, line: int) -> str:
    lines = content.splitlines()
    return lines[line - 1] if 1 <= line <= len(lines) else ""


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one web/src-equivalent ``root`` and return RAW v1.1 violation dicts.

    Emits ``RULE_COMMONS`` for any GSAP import under ``commons/``; otherwise emits
    ``RULE_LAYER`` for any GSAP import outside a ``presentation/`` layer. A GSAP
    import inside ``presentation/`` is clean and produces nothing. ``file`` is
    relative to ``root``; ``source_line`` is the RAW offending import line.
    """
    root = Path(root)
    exclude_globs = exclude_globs or []
    violations: list[dict] = []
    for ts_file in _collect_ts_files(root, exclude_globs):
        try:
            content = ts_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found = find_gsap_import(content)
        if found is None:
            continue
        matched_import, line = found
        try:
            rel = ts_file.relative_to(root)
        except ValueError:
            rel = ts_file
        rel_parts = rel.parts

        if rel_parts and rel_parts[0] == "commons":
            violations.append({
                "rule_id": RULE_COMMONS,
                "file": str(rel),
                "line": line,
                "col": 0,
                "evidence": f"GSAP imported in commons module: {matched_import}",
                "source_line": _line_text(content, line),
            })
        elif not is_presentation_layer(rel_parts):
            violations.append({
                "rule_id": RULE_LAYER,
                "file": str(rel),
                "line": line,
                "col": 0,
                "evidence": f"GSAP imported outside the presentation layer: {matched_import}",
                "source_line": _line_text(content, line),
            })
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan every root and return the concatenated RAW violation list."""
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
