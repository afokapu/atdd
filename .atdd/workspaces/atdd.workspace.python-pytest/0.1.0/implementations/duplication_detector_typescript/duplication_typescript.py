"""python-pytest detector for coder.duplication.no-intra-layer-code-typescript.

Realizes the agnostic obligation `coder.duplication.no-intra-layer-code-
typescript` (disposition `strict`) for the TypeScript/Preact stack: no
structurally identical code fragment may be duplicated across DIFFERENT files of
the SAME architectural layer under the frontend source root. Because there is no
tree-sitter dependency, the fingerprint is regex-based structural normalization
hashed over a sliding window of >= 7 non-trivial lines.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_duplication_detector_typescript.py
        :: determine_layer_from_path / _NORMALIZE_PATTERNS / _normalize_line /
           _is_trivial_line / extract_ts_fragments / find_intra_layer_duplicates_ts
    (read-only core). The detection logic is copied in spirit; the
    ``atdd.coach.*`` substrate couplings were REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_DUP_TS`` constant. Authoritative
    metadata (severity 2; disposition strict) lives in the convention node.
  * ``Violation``  -> plain dicts in the v1.1 violation-output shape
    ``{rule_id, file, line, col, evidence, source_line}`` (PROVIDER-CONTRACT-v1.1
    §3.2). ``source_line`` carries the RAW offending line (the first site).
  * ``find_repo_root`` + ``.atdd/config.yaml`` load  -> REMOVED. Scan scope is
    supplied explicitly via ``ATDD_SCAN_ROOTS`` / ``ATDD_SCAN_EXCLUDES`` (§2);
    ``min_lines`` and the layer set are module constants matching core defaults.
  * ``assert_disposition_satisfied``  -> NOT PORTED. The detector emits RAW
    violations only; the strict verdict is the downstream consumer's (§1).

Files of multiple roots are pooled and grouped by layer BEFORE comparison
(core-faithful single by-layer map). Pure stdlib (``re``, ``hashlib``,
``fnmatch``, ``pathlib``) — no core imports.
"""
from __future__ import annotations

import fnmatch
import hashlib
import re
from pathlib import Path

# The convention rule_id this detector realizes.
RULE_DUP_TS = "coder.duplication.no-intra-layer-code-typescript"  # disposition: strict

# Minimum non-trivial normalized lines in a fragment (core convention default).
MIN_LINES = 7

# Architectural layers compared (files outside these classify as 'unknown').
LAYERS = ("domain", "application", "presentation", "integration")

_TS_EXTENSIONS = (".ts", ".tsx")
_SKIP_DIRS = frozenset(
    {".git", "node_modules", "dist", "build", ".next", ".nuxt", "coverage",
     "__pycache__", ".cache"}
)


def determine_layer_from_path(file_path: Path) -> str:
    """Determine the architectural layer of a TypeScript ``file_path`` (core-faithful)."""
    path_str = str(file_path).lower()

    if "/domain/" in path_str:
        return "domain"
    elif "/application/" in path_str:
        return "application"
    elif "/presentation/" in path_str:
        return "presentation"
    elif "/integration/" in path_str or "/infrastructure/" in path_str:
        return "integration"

    if "/entities/" in path_str or "/models/" in path_str or "/value_objects/" in path_str:
        return "domain"
    elif "/use_cases/" in path_str or "/usecases/" in path_str or "/hooks/" in path_str:
        return "application"
    elif "/components/" in path_str or "/pages/" in path_str or "/views/" in path_str:
        return "presentation"
    elif "/adapters/" in path_str or "/clients/" in path_str or "/api/" in path_str:
        return "integration"

    return "unknown"


# Patterns for normalization (order matters) — copied from core.
_NORMALIZE_PATTERNS = [
    (re.compile(r"//.*$", re.MULTILINE), ""),
    (re.compile(r"/\*.*?\*/", re.DOTALL), ""),
    (re.compile(r"'[^']*'"), '"S"'),
    (re.compile(r'"[^"]*"'), '"S"'),
    (re.compile(r"`[^`]*`"), '"S"'),
    (re.compile(r"\b\d+\.?\d*\b"), "0"),
    (re.compile(
        r"\b(?!(?:import|export|from|const|let|var|function|class|interface|type|"
        r"if|else|for|while|do|switch|case|break|continue|return|throw|try|catch|"
        r"finally|new|delete|typeof|instanceof|void|in|of|as|is|async|await|"
        r"extends|implements|static|get|set|public|private|protected|readonly|"
        r"abstract|override|enum|namespace|module|declare|default|yield|super|"
        r"this|true|false|null|undefined|never|any|string|number|boolean|object|"
        r"unknown|void|Promise|Array|Map|Set|Record)\b)[a-zA-Z_$][a-zA-Z0-9_$]*"
    ), "ID"),
]


def _normalize_line(line: str) -> str:
    """Normalize a TypeScript line to structural form."""
    result = line.strip()
    if not result:
        return ""
    for pattern, replacement in _NORMALIZE_PATTERNS:
        result = pattern.sub(replacement, result)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _is_trivial_line(normalized: str) -> bool:
    """Check if a normalized line is trivial (braces, empty, single tokens)."""
    return normalized in ("", "{", "}", "};", ");", "],", ")", "]", "});", "});")


def extract_ts_fragments(file_path: Path, min_lines: int) -> list[tuple[str, int, int]]:
    """Extract hashable fragments — (hash, start_line, end_line)."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = source.splitlines()
    non_trivial: list[tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        normalized = _normalize_line(line)
        if not _is_trivial_line(normalized):
            non_trivial.append((i, normalized))

    if len(non_trivial) < min_lines:
        return []

    fragments: list[tuple[str, int, int]] = []
    for i in range(len(non_trivial) - min_lines + 1):
        window = non_trivial[i:i + min_lines]
        block = "\n".join(line for _, line in window)
        h = hashlib.sha256(block.encode("utf-8")).hexdigest()[:16]
        start_line = window[0][0]
        end_line = window[-1][0]
        fragments.append((h, start_line, end_line))

    return fragments


def find_intra_layer_duplicates_ts(
    files_by_layer: dict[str, list[Path]], min_lines: int
) -> list[dict]:
    """Find duplicate fragments within the same layer, across DIFFERENT files."""
    violations: list[dict] = []

    for layer, files in files_by_layer.items():
        if len(files) < 2:
            continue

        hash_map: dict[str, list[tuple[Path, int, int]]] = {}
        for f in files:
            for h, start, end in extract_ts_fragments(f, min_lines):
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
                    "lines": min_lines,
                })

    return violations


def is_excluded(ts_file: Path) -> bool:
    """True when ``ts_file`` is out of scope (test/spec, declaration, barrel)."""
    name = ts_file.name
    if name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", ".d.ts")):
        return True
    if name == "index.ts":
        return True
    if "__tests__" in ts_file.parts:
        return True
    return False


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def _collect_files(scan_root: Path, exclude_globs: list[str]) -> list[tuple[Path, Path]]:
    """In-scope ``*.ts``/``*.tsx`` files as (absolute, relative) pairs."""
    if not scan_root.exists():
        return []
    out: list[tuple[Path, Path]] = []
    for p in sorted(scan_root.rglob("*")):
        if not p.is_file() or p.suffix not in _TS_EXTENSIONS:
            continue
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
    """Scan every root, pool files by layer, return RAW v1.1 violation dicts."""
    exclude_globs = exclude_globs or []
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
    for v in find_intra_layer_duplicates_ts(files_by_layer, MIN_LINES):
        rel_a = rel_of.get(v["file_a"], v["file_a"])
        rel_b = rel_of.get(v["file_b"], v["file_b"])
        violations.append({
            "rule_id": RULE_DUP_TS,
            "file": str(rel_a),
            "line": v["line_a"],
            "col": 0,
            "evidence": (
                f"[{v['layer']}] {rel_a}:{v['line_a']} <-> {rel_b}:{v['line_b']} "
                f"({v['lines']} identical normalized lines)"
            ),
            "source_line": _line_text(v["file_a"], v["line_a"]),
        })
    return violations
