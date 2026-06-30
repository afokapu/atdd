"""python-pytest detector for coder.dead-code.reachability-typescript.

Realizes the agnostic obligation ``coder.dead-code.reachability-typescript``
(disposition ``strict``, severity 2): every production ``*.ts``/``*.tsx`` file
must be reachable from at least one graph root via the import graph.

NOTE ON STACK — this is a PYTHON detector that INSPECTS TypeScript source. The
reachability check is regex-over-text (import/export/require/dynamic-import
specifiers), which needs no TypeScript runtime, so it runs natively under the
python-pytest provider exactly as the core validator did (core
``test_dead_code_typescript.py`` is itself a Python pytest module). This is
distinct from PHASE05-PROOF §6 gap 4 (validators that need a real TS runtime and
a separate node/vitest workspace) — this one does not.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_dead_code_typescript.py
        :: find_typescript_files / is_root_file / extract_import_paths /
           resolve_import_to_file / _add_candidates / build_file_import_graph /
           find_reachable_files / build_reverse_graph / test_no_unreachable_typescript_files
    (origin/main, blob 4aa29893109e008f). Regex import logic copied in spirit;
    the ``atdd.coach.*`` substrate couplings were REMOVED. Convention provenance:
    src/atdd/coder/conventions/dead-code.convention.yaml (blob 819ab6f232fb9a84),
    rule ``coder.dead-code.reachability-typescript``.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule("coder.dead-code.reachability-typescript")``  -> module-level
    ``RULE_DEAD_CODE_TS`` constant. Severity 2 / disposition strict live in the
    convention node.
  * ``Violation``  -> plain dicts ``{rule_id, file, line, col, evidence,
    source_line}`` (v1.1 §3.2). An unreachable file is reported at
    ``line=1, col=0``; ``file`` is relative to its scan root; ``source_line`` is
    the file's first line.
  * ``find_repo_root`` + the hardcoded ``REPO_ROOT/web/src`` scan  -> REMOVED.
    Scan scope is supplied explicitly via ``ATDD_SCAN_ROOTS`` (§2); each scan
    root doubles as the ``@/`` path-alias anchor (core's ``WEB_SRC`` role).
  * ratchet baseline  -> NOT PORTED (downstream consumer disposition concern).

Pure stdlib (``re``, ``os``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import fnmatch
import os
import re
from collections import deque
from pathlib import Path

# The convention rule_id this detector realizes.
RULE_DEAD_CODE_TS = "coder.dead-code.reachability-typescript"  # disposition: strict

_TS_EXTENSIONS = (".ts", ".tsx")
_SKIP_DIRS = frozenset(
    {".git", "node_modules", "dist", "build", ".next", ".nuxt",
     "coverage", "__pycache__", ".cache", "__tests__", "__mocks__"}
)

# index.ts/.tsx is the TS equivalent of __init__.py — structural barrel + root.
ROOT_FILENAMES = frozenset({"index.ts", "index.tsx", "wagon.ts", "composition.ts"})
_ENTRY_FILENAMES = frozenset({"main.ts", "main.tsx", "app.ts", "app.tsx"})
_TEST_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")
_TEST_DIRS = frozenset({"__tests__", "tests", "test"})
_STRUCTURAL = frozenset({"index.ts", "index.tsx"})

_IMPORT_FROM_RE = re.compile(r"""(?:^|\n)\s*import\s+(?:[\s\S]*?)\s+from\s+['"]([^'"]+)['"]""")
_EXPORT_FROM_RE = re.compile(r"""(?:^|\n)\s*export\s+(?:[\s\S]*?)\s+from\s+['"]([^'"]+)['"]""")
_IMPORT_SIDE_EFFECT_RE = re.compile(r"""(?:^|\n)\s*import\s+['"]([^'"]+)['"]""")
_REQUIRE_RE = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""")
_DYNAMIC_IMPORT_RE = re.compile(r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)""")
_ALL_PATTERNS = (
    _IMPORT_FROM_RE, _EXPORT_FROM_RE, _IMPORT_SIDE_EFFECT_RE, _REQUIRE_RE, _DYNAMIC_IMPORT_RE,
)


def is_test_file(file_path: Path) -> bool:
    name = file_path.name
    if any(name.endswith(s) for s in _TEST_SUFFIXES):
        return True
    return any(parent.name in _TEST_DIRS for parent in file_path.parents)


def is_root_file(file_path: Path) -> bool:
    """Roots: index barrels, test files, composition/wagon roots, app entry points."""
    name = file_path.name
    if name in ROOT_FILENAMES:
        return True
    if is_test_file(file_path):
        return True
    if name in _ENTRY_FILENAMES:
        return True
    return False


def extract_import_paths(file_path: Path) -> list[str]:
    """Extract raw import specifier strings from a TS file via regex."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    specifiers: list[str] = []
    for pattern in _ALL_PATTERNS:
        specifiers.extend(pattern.findall(source))
    return specifiers


def _add_candidates(resolved: Path, candidates: set[Path], all_files: set[Path]) -> None:
    for ext in _TS_EXTENSIONS:
        c = resolved.with_suffix(ext)
        if c in all_files:
            candidates.add(c)
    for ext in _TS_EXTENSIONS:
        idx = resolved / f"index{ext}"
        if idx in all_files:
            candidates.add(idx)
    if resolved in all_files:
        candidates.add(resolved)


def resolve_import_to_file(
    specifier: str, source_file: Path, all_files: set[Path], *, root: Path
) -> set[Path]:
    """Resolve a TS import specifier to file candidates (relative or ``@/`` alias)."""
    candidates: set[Path] = set()
    if specifier.startswith("."):
        resolved = (source_file.parent / specifier).resolve()
        _add_candidates(resolved, candidates, all_files)
    elif specifier.startswith("@/"):
        resolved = (root / specifier[2:]).resolve()
        _add_candidates(resolved, candidates, all_files)
    # External (npm) specifiers are outside our graph.
    return candidates


def _collect_files(root: Path, exclude_globs: list[str]) -> list[Path]:
    """All ``*.ts``/``*.tsx`` under ``root`` (skip vendored dirs + excluded globs)."""
    if not root.exists():
        return []
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(_TS_EXTENSIONS):
                continue
            p = Path(dirpath) / fname
            rel = p.relative_to(root)
            if exclude_globs and any(fnmatch.fnmatch(str(rel), pat) for pat in exclude_globs):
                continue
            files.append(p)
    return sorted(files)


def build_file_import_graph(ts_files: list[Path], *, root: Path) -> dict[Path, set[Path]]:
    all_files = set(ts_files)
    graph: dict[Path, set[Path]] = {f: set() for f in ts_files}
    for ts_file in ts_files:
        for spec in extract_import_paths(ts_file):
            graph[ts_file].update(resolve_import_to_file(spec, ts_file, all_files, root=root))
    return graph


def find_reachable_files(roots: set[Path], graph: dict[Path, set[Path]]) -> set[Path]:
    visited: set[Path] = set()
    queue = deque(roots)
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in graph.get(current, set()):
            if neighbor not in visited:
                queue.append(neighbor)
    return visited


def build_reverse_graph(graph: dict[Path, set[Path]]) -> dict[Path, set[Path]]:
    reverse: dict[Path, set[Path]] = {f: set() for f in graph}
    for source, targets in graph.items():
        for target in targets:
            if target in reverse:
                reverse[target].add(source)
    return reverse


def _first_line(ts_file: Path) -> str:
    try:
        with ts_file.open(encoding="utf-8", errors="replace") as fh:
            return fh.readline().rstrip("\n")
    except OSError:
        return ""


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one ``root`` (the ``@/`` anchor) and return RAW v1.1 violation dicts."""
    root = Path(root)
    exclude_globs = exclude_globs or []
    ts_files = _collect_files(root, exclude_globs)
    if not ts_files:
        return []

    graph = build_file_import_graph(ts_files, root=root)
    roots = {f for f in ts_files if is_root_file(f)}
    if not roots:
        return []

    reachable = find_reachable_files(roots, graph)
    reverse_reachable = find_reachable_files(roots, build_reverse_graph(graph))
    all_reachable = reachable | reverse_reachable

    violations: list[dict] = []
    for ts_file in ts_files:
        if ts_file in all_reachable:
            continue
        if ts_file.name in _STRUCTURAL:
            continue  # index.ts/.tsx is structural like __init__.py
        try:
            rel = ts_file.relative_to(root)
        except ValueError:
            rel = ts_file
        violations.append(
            {
                "rule_id": RULE_DEAD_CODE_TS,
                "file": str(rel),
                "line": 1,
                "col": 0,
                "evidence": f"unreachable TypeScript file: {rel}",
                "source_line": _first_line(ts_file),
            }
        )
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
