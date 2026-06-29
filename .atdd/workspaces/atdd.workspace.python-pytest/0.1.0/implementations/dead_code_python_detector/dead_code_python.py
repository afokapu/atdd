"""python-pytest detector for coder.dead-code.reachability (Python).

Realizes the agnostic obligation ``coder.dead-code.reachability`` (disposition
``strict``, severity 2) for the Python stack: every production ``*.py`` file must
be reachable from at least one graph root via the import graph.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_dead_code_python.py
        :: find_python_files / is_root_file / _resolve_module_name /
           extract_imports_ast / resolve_module_to_file / build_file_import_graph /
           find_reachable_files / build_reverse_graph / test_no_unreachable_python_files
    (origin/main, blob cc94e3b115c6bdd3). The AST reachability logic is copied in
    spirit; the ``atdd.coach.*`` substrate couplings were REMOVED. Convention
    provenance: src/atdd/coder/conventions/dead-code.convention.yaml
    (blob 819ab6f232fb9a84), rule ``coder.dead-code.reachability``.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule("coder.dead-code.reachability")``  -> module-level
    ``RULE_DEAD_CODE_PY`` constant. Severity 2 / disposition strict live in the
    convention node, not bound at import.
  * ``Violation``  -> plain dicts in the v1.1 violation-output shape
    ``{rule_id, file, line, col, evidence, source_line}`` (PROVIDER-CONTRACT-v1.1
    §3.2). An unreachable file is reported at ``line=1, col=0``; ``source_line``
    is the file's first line (RAW, factual). ``file`` is relative to its scan root.
  * ``find_repo_root`` + the hardcoded ``REPO_ROOT/python`` scan  -> REMOVED.
    Scan scope is supplied explicitly via ``ATDD_SCAN_ROOTS`` (§2); each scan
    root doubles as the package-resolution anchor (core's ``PYTHON_DIR`` role).
  * pyproject ``[project.scripts]`` CLI-entry-point roots  -> NOT PORTED. That is
    consumer SCAN-POLICY (it reads the repo's pyproject.toml); the hermetic
    detector keeps only convention roots (composition.py, wagon.py, conftest.py,
    __init__.py, test files) + the composition.py -> wagon ``src/`` subtree reach.
  * ratchet baseline  -> NOT PORTED. Ratchet/baseline is a downstream consumer
    disposition concern (PHASE05-PROOF §6); the detector emits RAW unreachable
    files and the consumer applies ``strict`` (any unreachable -> FAIL).

Pure stdlib (``ast``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import ast
import fnmatch
from collections import deque
from pathlib import Path

# The convention rule_id this detector realizes.
RULE_DEAD_CODE_PY = "coder.dead-code.reachability"  # disposition: strict

# Files that are always graph roots by convention.
ROOT_FILENAMES = frozenset({"composition.py", "wagon.py", "conftest.py"})
TEST_DIRS = frozenset({"test", "tests"})


def is_test_file(file_path: Path) -> bool:
    """test_*.py / *_test.py / any file under a test|tests directory."""
    name = file_path.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return any(parent.name in TEST_DIRS for parent in file_path.parents)


def is_root_file(file_path: Path) -> bool:
    """Graph roots: tests, composition.py, wagon.py, conftest.py, __init__.py."""
    name = file_path.name
    if name in ROOT_FILENAMES:
        return True
    if is_test_file(file_path):
        return True
    if name == "__init__.py":
        return True
    return False


def _resolve_module_name(importer: Path, module: str | None, level: int, *, root: Path) -> str | None:
    """Resolve an ``ast.ImportFrom`` to an absolute dotted module path (anchored at ``root``)."""
    if level == 0:
        return module
    try:
        rel = importer.relative_to(root)
    except ValueError:
        return None
    pkg_parts = list(rel.parent.parts)
    if level - 1 > len(pkg_parts):
        return None
    base = pkg_parts[: len(pkg_parts) - (level - 1)]
    suffix = module.split(".") if module else []
    parts = base + suffix
    return ".".join(parts) if parts else None


def extract_imports_ast(file_path: Path, *, root: Path) -> list[str]:
    """Extract (absolute) dotted import module paths from a Python file via AST."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError, OSError, ValueError):
        return []

    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_module_name(file_path, node.module, node.level, root=root)
            if resolved is None:
                continue
            modules.append(resolved)
            if node.level >= 1:
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    modules.append(f"{resolved}.{alias.name}")
    return modules


def resolve_module_to_file(module_path: str, all_files: set[Path], *, root: Path) -> set[Path]:
    """Resolve a dotted module path to file candidates under ``root``."""
    parts = module_path.split(".")
    candidates: set[Path] = set()
    file_candidate = root / "/".join(parts)

    py_candidate = file_candidate.with_suffix(".py")
    if py_candidate in all_files:
        candidates.add(py_candidate)

    init_candidate = file_candidate / "__init__.py"
    if init_candidate in all_files:
        candidates.add(init_candidate)

    if file_candidate.is_dir():
        init_file = file_candidate / "__init__.py"
        if init_file in all_files:
            candidates.add(init_file)
    return candidates


def build_file_import_graph(python_files: list[Path], *, root: Path) -> dict[Path, set[Path]]:
    """File -> set of files it imports (directly or via package __init__.py)."""
    all_files = set(python_files)
    graph: dict[Path, set[Path]] = {f: set() for f in python_files}
    for py_file in python_files:
        for module_path in extract_imports_ast(py_file, root=root):
            graph[py_file].update(resolve_module_to_file(module_path, all_files, root=root))
    return graph


def find_reachable_files(roots: set[Path], graph: dict[Path, set[Path]]) -> set[Path]:
    """BFS from ``roots`` through ``graph``; return all visited files."""
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
    """Reverse import graph (who imports this file?)."""
    reverse: dict[Path, set[Path]] = {f: set() for f in graph}
    for source, targets in graph.items():
        for target in targets:
            if target in reverse:
                reverse[target].add(source)
    return reverse


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def _collect_files(root: Path, exclude_globs: list[str]) -> list[Path]:
    """All ``*.py`` under ``root`` (excluding __pycache__ + supplied globs)."""
    if not root.exists():
        return []
    out: list[Path] = []
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        try:
            rel = p.relative_to(root)
        except ValueError:
            rel = p
        if exclude_globs and _matches_exclude(rel, exclude_globs):
            continue
        out.append(p)
    return out


def _first_line(py_file: Path) -> str:
    try:
        with py_file.open(encoding="utf-8") as fh:
            return fh.readline().rstrip("\n")
    except (OSError, UnicodeDecodeError):
        return ""


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one ``root`` (a package anchor) and return RAW v1.1 violation dicts.

    Each violation is an unreachable ``*.py`` file (not ``__init__.py``) reported
    at ``line=1, col=0``; ``file`` is relative to ``root``.
    """
    root = Path(root)
    exclude_globs = exclude_globs or []
    python_files = _collect_files(root, exclude_globs)
    if not python_files:
        return []

    graph = build_file_import_graph(python_files, root=root)
    roots = {f for f in python_files if is_root_file(f)}
    if not roots:
        return []

    # composition.py implicitly reaches every file in its sibling src/ subtree
    # (DI wiring the static tracer can't follow) — core parity.
    for comp_root in {f for f in roots if f.name == "composition.py"}:
        src_dir = comp_root.parent / "src"
        if src_dir.is_dir():
            for py_file in python_files:
                if str(py_file).startswith(str(src_dir)):
                    roots.add(py_file)

    reachable = find_reachable_files(roots, graph)
    reverse_reachable = find_reachable_files(roots, build_reverse_graph(graph))
    all_reachable = reachable | reverse_reachable

    violations: list[dict] = []
    for py_file in python_files:
        if py_file in all_reachable:
            continue
        if py_file.name == "__init__.py":
            continue  # structural, not dead code
        try:
            rel = py_file.relative_to(root)
        except ValueError:
            rel = py_file
        violations.append(
            {
                "rule_id": RULE_DEAD_CODE_PY,
                "file": str(rel),
                "line": 1,
                "col": 0,
                "evidence": f"unreachable Python file: {rel}",
                "source_line": _first_line(py_file),
            }
        )
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan every root and return the concatenated RAW violation list."""
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
