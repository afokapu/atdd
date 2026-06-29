"""python-pytest detector for coder.refactor.composition-consumer (+ -root).

Realizes the agnostic intra-feature composition-completeness obligation for the
PYTHON stack (both rule_ids disposition `strict`):

  * coder.refactor.composition-consumer — every implementation file in a source
    layer (domain/application/integration) has at least one valid upstream
    consumer per the composition layer rules.
  * coder.refactor.composition-root     — a feature's `composition.py` reaches
    every EXISTING layer of that feature via imports or called-setter wiring.

ONE run carries TWO distinct rule_ids — the v1.1 multi-rule output channel
(PROVIDER-CONTRACT-v1.1.md §3).

SCOPE (honest): this is the PYTHON realization only. Core's validator also covers
the TypeScript and Supabase stacks (tsconfig path-alias resolution, barrel
re-exports). Per the documented `-python` / `-typescript` provider split
(PHASE05-PROOF §6.4), the TS/Supabase realizations are SEPARATE detectors in a
separate workspace package and are out of scope for this wave. The obligation
node is stack-agnostic; this detector is the Python leg.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_composition_completeness.py
        :: detect_layer / is_test_file / graph_file_excluded / candidate_source_file
           / find_feature_dirs / build_feature_contexts / extract_python_imports
           / resolve_python_import / build_python_graph (incl. setter wiring) / bfs
           / build_reverse_graph / feature_rule_violations
           / python_composition_root_violations
    (origin/main @ 624d3afe, blob aca618a4d9e3b527). The graph/BFS/setter logic is
    copied behavior-for-behavior; the `atdd.coach.*` substrate couplings were
    REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_CONSUMER`` / ``RULE_ROOT``
    constants. Authoritative metadata (severity 3; both strict) lives in the
    convention nodes.
  * ``Violation``  -> plain dicts in the v1.1 shape
    ``{rule_id, file, line, col, evidence, source_line}`` (§3.2). The core
    ``location = feature_id/file_rel`` + ``detail`` (with spec_id) are preserved
    inside ``file`` (scan-root-relative path) and ``evidence``.
  * ``find_repo_root`` + ``ScanRoot`` + ``is_excluded_fixture`` dual-dir scan
    -> REMOVED. Each ``ATDD_SCAN_ROOTS`` entry is a python stack root and is used
    as BOTH the discovery root and the import root (the consumer ``python/`` case,
    ``import_prefix=""``). The toolkit ``src/atdd`` dogfood carve-out and the
    negative-fixture self-trigger guard were consumer scan-policy, not detector
    logic (§2).
  * The ``composition.convention.yaml`` ``layer_rules`` / ``composition_root_rule``
    -> VENDORED as the module constants ``PY_LAYER_RULES`` / ``ROOT_SPEC_ID``
    below (copied verbatim from the convention, blob dae07ff4caa21cac), so the
    detector needs no YAML load.
  * ``assert_disposition_satisfied`` (ratchet baseline) -> NOT PORTED; both
    rule_ids are strict, aggregated downstream by the consumer (§1).

Pure stdlib (``ast``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import ast
from collections import deque
from pathlib import Path

RULE_CONSUMER = "coder.refactor.composition-consumer"  # disposition: strict
RULE_ROOT = "coder.refactor.composition-root"          # disposition: strict

LAYER_NAMES = ("domain", "application", "integration", "presentation")
PY_CONNECTOR_FILES = {"__init__.py"}

# Vendored from composition.convention.yaml -> composition.stacks.python (verbatim).
# Each rule: a source layer and the set of layers a valid consumer may live in.
PY_LAYER_RULES = (
    {"spec_id": "SPEC-CODER-COMP-0001", "source_layer": "application",
     "consumer_layers": ("presentation", "composition")},
    {"spec_id": "SPEC-CODER-COMP-0002", "source_layer": "integration",
     "consumer_layers": ("application", "composition")},
    {"spec_id": "SPEC-CODER-COMP-0003", "source_layer": "domain",
     "consumer_layers": ("application", "integration", "presentation", "composition")},
)
ROOT_SPEC_ID = "SPEC-CODER-COMP-0004"  # composition_root_rule.spec_id


# ── graph + layer helpers (ported behavior-for-behavior) ──────────────────────


def is_test_file(path: Path) -> bool:
    name = path.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return any(part in {"test", "tests", "test_fixtures"} for part in path.parts)


def graph_file_excluded(path: Path) -> bool:
    if "__pycache__" in path.parts:
        return True
    if any(part in {"node_modules", "dist", "commons", "shared"} for part in path.parts):
        return True
    return is_test_file(path)


def candidate_source_file(path: Path) -> bool:
    if graph_file_excluded(path):
        return False
    if path.name in PY_CONNECTOR_FILES:
        return False
    return True


def detect_layer(path: Path) -> str:
    if path.name in {"composition.py", "wagon.py"}:
        return "composition"
    for layer in LAYER_NAMES:
        if layer in path.parts:
            return layer
    return "unknown"


def bfs(start_nodes, graph: dict) -> set:
    visited: set = set()
    queue = deque(start_nodes)
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in graph.get(current, set()):
            if neighbor not in visited:
                queue.append(neighbor)
    return visited


def build_reverse_graph(graph: dict) -> dict:
    reverse: dict = {node: set() for node in graph}
    for source, targets in graph.items():
        for target in targets:
            reverse.setdefault(target, set()).add(source)
    return reverse


# ── feature discovery ─────────────────────────────────────────────────────────


class FeatureContext:
    def __init__(self, root: Path, feature_dir: Path, layer_files: dict, root_files: list):
        self.root = root
        self.feature_dir = feature_dir
        self.layer_files = layer_files
        self.root_files = root_files

    @property
    def feature_id(self) -> str:
        return str(self.feature_dir.relative_to(self.root))


def feature_dir_for_layer_dir(layer_dir: Path) -> Path | None:
    # python layout: {wagon}/{feature}/src/{layer}/
    if layer_dir.parent.name != "src":
        return None
    return layer_dir.parent.parent


def find_feature_dirs(root: Path) -> set:
    feature_dirs: set = set()
    if not root.exists():
        return feature_dirs
    for layer in LAYER_NAMES:
        for layer_dir in root.rglob(layer):
            if not layer_dir.is_dir():
                continue
            feature_dir = feature_dir_for_layer_dir(layer_dir)
            if feature_dir is None or feature_dir == root:
                continue
            feature_dirs.add(feature_dir)
    return feature_dirs


def root_files_for_feature(feature_dir: Path) -> list:
    roots = []
    for name in ("composition.py", "wagon.py"):
        candidate = feature_dir / name
        if candidate.exists():
            roots.append(candidate)
    return roots


def build_feature_contexts(root: Path) -> list:
    contexts: list = []
    for feature_dir in sorted(find_feature_dirs(root)):
        layer_files: dict = {}
        layer_root = feature_dir / "src"
        for layer in LAYER_NAMES:
            files: list = []
            layer_dir = layer_root / layer
            if layer_dir.exists():
                for file_path in sorted(layer_dir.rglob("*.py")):
                    if not file_path.is_file():
                        continue
                    if graph_file_excluded(file_path):
                        continue
                    files.append(file_path)
            layer_files[layer] = files
        contexts.append(FeatureContext(root, feature_dir, layer_files,
                                       root_files_for_feature(feature_dir)))
    return contexts


# ── python import graph (ported) ──────────────────────────────────────────────


class PythonImportRef:
    def __init__(self, module: str, names: tuple, level: int):
        self.module = module
        self.names = names
        self.level = level


def collect_python_files(root: Path) -> list:
    if not root.exists():
        return []
    return sorted(
        p for p in root.rglob("*.py")
        if p.is_file() and not graph_file_excluded(p)
    )


def find_python_feature_root(file_path: Path) -> Path | None:
    if file_path.name in {"composition.py", "wagon.py"} and (file_path.parent / "src").exists():
        return file_path.parent
    current = file_path.parent
    while current != current.parent:
        if current.name == "src":
            return current.parent
        current = current.parent
    return None


def candidate_python_paths(base_path: Path, all_files: set) -> set:
    candidates: set = set()
    if base_path.suffix == ".py":
        if base_path in all_files:
            candidates.add(base_path)
    else:
        py_file = base_path.with_suffix(".py")
        init_file = base_path / "__init__.py"
        if py_file in all_files:
            candidates.add(py_file)
        if init_file in all_files:
            candidates.add(init_file)
    return candidates


def resolve_python_import(source_file: Path, import_ref: PythonImportRef,
                          all_files: set, import_root: Path) -> set:
    """Resolve an import to candidate target files (single-root: import_root)."""
    candidates: set = set()
    if import_ref.level > 0:
        base_dir = source_file.parent
        for _ in range(import_ref.level - 1):
            base_dir = base_dir.parent
        relative_base = (base_dir / import_ref.module.replace(".", "/")
                         if import_ref.module else base_dir)
        candidates.update(candidate_python_paths(relative_base, all_files))
    if import_ref.module:
        top_level = import_ref.module.split(".", 1)[0]
        feature_root = find_python_feature_root(source_file)
        if feature_root and top_level in LAYER_NAMES:
            local_base = feature_root / "src" / import_ref.module.replace(".", "/")
            candidates.update(candidate_python_paths(local_base, all_files))
        repo_base = import_root / import_ref.module.replace(".", "/")
        candidates.update(candidate_python_paths(repo_base, all_files))
    return candidates


def extract_python_imports(file_path: Path) -> list:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    refs: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                refs.append(PythonImportRef(alias.name, (alias.asname or alias.name,), 0))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = tuple(alias.asname or alias.name for alias in node.names)
            refs.append(PythonImportRef(module, names, node.level))
    return refs


def extract_called_names(file_path: Path) -> set:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    called: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
    return called


def build_python_graph(root: Path) -> dict:
    python_files = collect_python_files(root)
    all_files = set(python_files)
    graph: dict = {file_path: set() for file_path in python_files}
    for file_path in python_files:
        called_names = (extract_called_names(file_path)
                        if file_path.name == "composition.py" else set())
        for import_ref in extract_python_imports(file_path):
            resolved = resolve_python_import(file_path, import_ref, all_files, root)
            # Setter-only imports into composition.py only count for presentation
            # if the setter is actually CALLED (the #955 setter-wiring fix).
            if file_path.name == "composition.py" and import_ref.names:
                setter_only = all(name.startswith("set_") for name in import_ref.names)
                if setter_only:
                    resolved = {
                        target for target in resolved
                        if detect_layer(target) != "presentation"
                        or any(name in called_names for name in import_ref.names)
                    }
            graph[file_path].update(resolved)
    return graph


# ── violation emitters (ported; emit RAW v1.1 dicts) ──────────────────────────


def _first_line(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                return line
    except (OSError, UnicodeDecodeError):
        pass
    return ""


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def valid_upstream_consumers(target_file: Path, reverse_graph: dict, allowed_layers: set) -> set:
    upstream = bfs(reverse_graph.get(target_file, set()), reverse_graph)
    return {path for path in upstream if detect_layer(path) in allowed_layers}


def local_consumer_candidates(feature: FeatureContext, allowed_layers: set) -> set:
    candidates: set = set()
    for layer in allowed_layers:
        if layer == "composition":
            candidates.update(feature.root_files)
            continue
        candidates.update(feature.layer_files.get(layer, []))
    return candidates


def feature_rule_violations(root: Path, feature: FeatureContext, reverse_graph: dict) -> list:
    violations: list = []
    for rule in PY_LAYER_RULES:
        spec_id = rule["spec_id"]
        source_layer = rule["source_layer"]
        allowed_layers = set(rule["consumer_layers"])
        for source_file in feature.layer_files.get(source_layer, []):
            if not candidate_source_file(source_file):
                continue
            if valid_upstream_consumers(source_file, reverse_graph, allowed_layers):
                continue
            if not local_consumer_candidates(feature, allowed_layers):
                continue
            consumer_desc = " or ".join(sorted(allowed_layers))
            file_rel = str(source_file.relative_to(feature.feature_dir))
            violations.append({
                "rule_id": RULE_CONSUMER,
                "file": _rel(root, source_file),
                "line": 1,
                "col": 0,
                "evidence": (
                    f"spec_id={spec_id} feature={feature.feature_id} file={file_rel} "
                    f"layer={source_layer} expected=imported_by_"
                    f"{consumer_desc.replace(' ', '_')} found=0_consumers — this "
                    f"{source_layer} file exists but is never consumed; add a valid "
                    f"downstream consumer or remove it"
                ),
                "source_line": _first_line(source_file),
            })
    return violations


def python_composition_root_violations(root: Path, feature: FeatureContext, graph: dict) -> list:
    composition_file = feature.feature_dir / "composition.py"
    if not composition_file.exists():
        return []
    reachable = bfs([composition_file], graph)
    existing_layers = {
        layer for layer, files in feature.layer_files.items()
        if any(candidate_source_file(path) for path in files)
    }
    reached_layers = {
        detect_layer(path) for path in reachable
        if path.is_relative_to(feature.feature_dir)
    }
    missing = sorted(existing_layers - reached_layers)
    if not missing:
        return []
    file_rel = str(composition_file.relative_to(feature.feature_dir))
    return [{
        "rule_id": RULE_ROOT,
        "file": _rel(root, composition_file),
        "line": 1,
        "col": 0,
        "evidence": (
            f"spec_id={ROOT_SPEC_ID} feature={feature.feature_id} file={file_rel} "
            f"layer=composition expected=reaches_all_existing_layers "
            f"found=missing_{','.join(missing)} — the feature composition root does "
            f"not reach every existing layer; import the missing layer directly or "
            f"wire it through a called setter"
        ),
        "source_line": _first_line(composition_file),
    }]


# ── public scan API (the v1.1 contract surface) ───────────────────────────────


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one python stack ``root`` and return RAW v1.1 violation dicts.

    Discovery root == import root == ``root`` (the consumer ``python/`` case).
    Emits both ``RULE_CONSUMER`` (unwired layer files) and ``RULE_ROOT``
    (composition.py that misses an existing layer).
    """
    root = Path(root)
    features = build_feature_contexts(root)
    if not features:
        return []
    graph = build_python_graph(root)
    reverse = build_reverse_graph(graph)
    violations: list = []
    for feature in features:
        violations.extend(feature_rule_violations(root, feature, reverse))
    for feature in features:
        violations.extend(python_composition_root_violations(root, feature, graph))
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
