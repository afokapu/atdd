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

SCOPE: all THREE stacks the core validator covers — PYTHON, TypeScript, and
Supabase — are realized here, matching the legacy oracle which enforces the same
rule_id across every stack (``test_composition_completeness.py`` ::
``analyze_python_repo`` / ``analyze_typescript_repo`` for ``stack=typescript``
and ``stack=supabase``). An earlier wave shipped only the Python leg, dropping
the TypeScript and Supabase realizations — a parity regression (the same
``coder.refactor.composition-consumer`` obligation went unenforced for those
stacks). The TS/Supabase legs are now ported and bound here.

PARITY NOTE — TS vs Supabase: the core convention gives BOTH stacks the IDENTICAL
``layer_rules`` (application→presentation, integration→application,
domain→{application,integration,presentation}), and ``analyze_typescript_repo``
emits ONLY ``coder.refactor.composition-consumer`` (no composition-root check for
the non-python stacks). Because ``composition`` is never an allowed consumer
layer for these stacks, the supabase-vs-typescript differences (``index.ts``
treated as the composition root / the ``detect_layer`` ``index.ts``→composition
rule) never change the consumer-rule verdict. The two are therefore realized by a
single non-python (TypeScript-family) graph leg over each scan root, with both a
TypeScript-shaped and a Supabase-shaped fixture proving the rule fires for each.

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
  * ``find_repo_root`` + ``ScanRoot`` dual-dir scan -> REMOVED. Each
    ``ATDD_SCAN_ROOTS`` entry is a stack root used as BOTH the discovery root and
    the import root (the consumer ``python/`` / ``web/src`` / ``supabase/functions``
    case, ``import_prefix=""``). The toolkit ``src/atdd`` dogfood carve-out was
    consumer scan-policy, not detector logic (§2).
  * ``is_excluded_fixture`` self-trigger guard -> PORTED (was previously dropped).
    The negative fixtures under this detector's ``fixtures/`` tree are
    intentionally broken; when a REAL tree is scanned they must never be
    discovered as features (or they would self-trigger the very violations they
    exist to test, #958). The guard is disabled only when the scan root is ITSELF
    inside the fixtures tree (the dogfood self-tests deliberately root the
    analyzer at a fixture), exactly as the legacy ``find_feature_dirs`` does.
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
import json
import re
from collections import deque
from pathlib import Path

RULE_CONSUMER = "coder.refactor.composition-consumer"  # disposition: strict
RULE_ROOT = "coder.refactor.composition-root"          # disposition: strict

LAYER_NAMES = ("domain", "application", "integration", "presentation")
PY_CONNECTOR_FILES = {"__init__.py"}
TS_CONNECTOR_FILES = {"index.ts", "index.tsx", "types.ts"}
TS_FILE_SUFFIXES = (".ts", ".tsx")
TEST_FILE_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts")

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

# Vendored from composition.convention.yaml -> composition.stacks.typescript and
# .supabase (verbatim). The two stacks share IDENTICAL layer_rules and neither
# admits ``composition`` as a consumer layer; see the module PARITY NOTE.
TS_LAYER_RULES = (
    {"spec_id": "SPEC-CODER-COMP-0001", "source_layer": "application",
     "consumer_layers": ("presentation",)},
    {"spec_id": "SPEC-CODER-COMP-0002", "source_layer": "integration",
     "consumer_layers": ("application",)},
    {"spec_id": "SPEC-CODER-COMP-0003", "source_layer": "domain",
     "consumer_layers": ("application", "integration", "presentation")},
)
SUPABASE_LAYER_RULES = TS_LAYER_RULES  # identical per the convention

# The negative-fixtures tree marker (legacy ``_toolkit_roots.FIXTURES_MARKER``,
# adapted to this detector's layout). A path under this marker is an intentionally
# broken fixture that must not be discovered as a real feature.
FIXTURES_MARKER = "composition_completeness_detector/fixtures"


# ── graph + layer helpers (ported behavior-for-behavior) ──────────────────────


def is_excluded_fixture(path: Path) -> bool:
    """True when *path* sits under this detector's negative-fixtures tree.

    Ported from legacy ``_toolkit_roots.is_excluded_fixture``: the fixtures are
    intentionally broken and must never be discovered as real features when a
    real tree is scanned (#958).
    """
    return FIXTURES_MARKER in path.as_posix()


def is_test_file(path: Path) -> bool:
    name = path.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    if name.endswith(TEST_FILE_SUFFIXES):
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
    if path.name in PY_CONNECTOR_FILES or path.name in TS_CONNECTOR_FILES:
        return False
    return True


def detect_layer(path: Path) -> str:
    name = path.name
    if name in {"composition.py", "wagon.py"}:
        return "composition"
    # supabase edge-function entry point is the composition root for that stack.
    if name == "index.ts" and "supabase" in path.parts and "functions" in path.parts:
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
    def __init__(self, root: Path, feature_dir: Path, layer_files: dict,
                 root_files: list, stack: str = "python"):
        self.root = root
        self.feature_dir = feature_dir
        self.layer_files = layer_files
        self.root_files = root_files
        self.stack = stack

    @property
    def feature_id(self) -> str:
        return str(self.feature_dir.relative_to(self.root))


def feature_layer_root(feature_dir: Path, stack: str) -> Path:
    # python nests layers under {feature}/src/{layer}; ts/supabase put them
    # directly under {feature}/{layer}.
    return feature_dir / "src" if stack == "python" else feature_dir


def feature_dir_for_layer_dir(layer_dir: Path, stack: str) -> Path | None:
    if stack == "python":
        # python layout: {wagon}/{feature}/src/{layer}/
        if layer_dir.parent.name != "src":
            return None
        return layer_dir.parent.parent
    # ts/supabase layout: {wagon}/{feature}/{layer}/
    return layer_dir.parent


def find_feature_dirs(root: Path, stack: str = "python") -> set:
    feature_dirs: set = set()
    if not root.exists():
        return feature_dirs
    # Skip negative fixtures only when the scanned root is a REAL tree — the
    # dogfood self-tests intentionally root the analyzer inside fixtures (#958).
    skip_fixtures = not is_excluded_fixture(root)
    for layer in LAYER_NAMES:
        for layer_dir in root.rglob(layer):
            if not layer_dir.is_dir():
                continue
            feature_dir = feature_dir_for_layer_dir(layer_dir, stack)
            if feature_dir is None or feature_dir == root:
                continue
            # Negative fixtures self-trigger — never discover them as features.
            if skip_fixtures and is_excluded_fixture(feature_dir):
                continue
            feature_dirs.add(feature_dir)
    return feature_dirs


def root_files_for_feature(feature_dir: Path, stack: str = "python") -> list:
    if stack == "python":
        roots = []
        for name in ("composition.py", "wagon.py"):
            candidate = feature_dir / name
            if candidate.exists():
                roots.append(candidate)
        return roots
    if stack == "supabase":
        candidate = feature_dir / "index.ts"
        return [candidate] if candidate.exists() else []
    # typescript: page / container orchestration roots.
    roots = []
    presentation_dir = feature_dir / "presentation"
    if presentation_dir.exists():
        roots.extend(sorted(presentation_dir.glob("*Page.tsx")))
        roots.extend(sorted(presentation_dir.glob("*Container.tsx")))
    return roots


def build_feature_contexts(root: Path, stack: str = "python") -> list:
    contexts: list = []
    for feature_dir in sorted(find_feature_dirs(root, stack)):
        layer_files: dict = {}
        layer_root = feature_layer_root(feature_dir, stack)
        for layer in LAYER_NAMES:
            files: list = []
            layer_dir = layer_root / layer
            if layer_dir.exists():
                pattern = "*.py" if stack == "python" else "*"
                for file_path in sorted(layer_dir.rglob(pattern)):
                    if not file_path.is_file():
                        continue
                    if stack != "python" and file_path.suffix not in TS_FILE_SUFFIXES:
                        continue
                    if graph_file_excluded(file_path):
                        continue
                    files.append(file_path)
            layer_files[layer] = files
        contexts.append(FeatureContext(root, feature_dir, layer_files,
                                       root_files_for_feature(feature_dir, stack),
                                       stack=stack))
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
    # Exclude negative fixtures only when scanning a REAL tree (#958).
    skip_fixtures = not is_excluded_fixture(root)
    return sorted(
        p for p in root.rglob("*.py")
        if p.is_file()
        and not graph_file_excluded(p)
        and not (skip_fixtures and is_excluded_fixture(p))
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


# ── typescript / supabase import graph (ported behavior-for-behavior) ─────────


class TypeScriptEdge:
    def __init__(self, module: str, is_type_only: bool, is_reexport: bool):
        self.module = module
        self.is_type_only = is_type_only
        self.is_reexport = is_reexport


def typescript_edges(file_path: Path) -> list:
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return []
    statements = re.findall(r"(?:^|\n)\s*(?:import|export)[\s\S]*?;", content)
    edges: list = []
    for statement in statements:
        module_match = re.search(r"from\s+['\"]([^'\"]+)['\"]", statement)
        if not module_match:
            continue
        stripped = statement.strip()
        edges.append(TypeScriptEdge(
            module=module_match.group(1),
            is_type_only=stripped.startswith("import type") or stripped.startswith("export type"),
            is_reexport=stripped.startswith("export"),
        ))
    return edges


def load_tsconfig_paths(root: Path) -> list:
    """Parse ``tsconfig.json`` ``compilerOptions.paths`` into (alias, targets, base)."""
    tsconfig_path = Path(root) / "tsconfig.json"
    if not tsconfig_path.exists():
        return []
    try:
        data = json.loads(tsconfig_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    compiler_options = data.get("compilerOptions", {})
    base_url = compiler_options.get("baseUrl", ".")
    base_dir = (Path(root) / base_url).resolve()
    path_map = compiler_options.get("paths", {})
    aliases: list = []
    for alias, targets in path_map.items():
        if isinstance(targets, list):
            aliases.append((alias, [str(t) for t in targets], base_dir))
    return aliases


def match_alias(alias: str, module: str) -> str | None:
    if "*" not in alias:
        return "" if module == alias else None
    prefix, suffix = alias.split("*", 1)
    if not module.startswith(prefix):
        return None
    if suffix and not module.endswith(suffix):
        return None
    end = len(module) - len(suffix) if suffix else len(module)
    return module[len(prefix):end]


def candidate_typescript_paths(base_path: Path, all_files: set) -> set:
    candidates: set = set()
    if base_path.suffix in TS_FILE_SUFFIXES:
        if base_path in all_files:
            candidates.add(base_path)
        return candidates
    for target in (
        base_path.with_suffix(".ts"),
        base_path.with_suffix(".tsx"),
        base_path / "index.ts",
        base_path / "index.tsx",
    ):
        if target in all_files:
            candidates.add(target)
    return candidates


def resolve_typescript_import(source_file: Path, module: str, all_files: set,
                              aliases) -> set:
    if module.startswith("."):
        return candidate_typescript_paths((source_file.parent / module).resolve(), all_files)
    for alias, targets, base_dir in aliases:
        wildcard = match_alias(alias, module)
        if wildcard is None:
            continue
        resolved: set = set()
        for target in targets:
            target_path = target.replace("*", wildcard)
            resolved.update(candidate_typescript_paths((base_dir / target_path).resolve(), all_files))
        if resolved:
            return resolved
    return set()


def collect_typescript_files(root: Path) -> list:
    if not root.exists():
        return []
    skip_fixtures = not is_excluded_fixture(root)
    files: list = []
    for suffix in TS_FILE_SUFFIXES:
        files.extend(root.rglob(f"*{suffix}"))
    return sorted(
        p for p in files
        if p.is_file()
        and not graph_file_excluded(p)
        and not (skip_fixtures and is_excluded_fixture(p))
    )


def build_typescript_graph(root: Path) -> dict:
    ts_files = collect_typescript_files(root)
    all_files = set(ts_files)
    aliases = load_tsconfig_paths(root)
    graph: dict = {file_path: set() for file_path in ts_files}
    for file_path in ts_files:
        for edge in typescript_edges(file_path):
            if edge.is_type_only:  # type-only imports are not composition evidence
                continue
            graph[file_path].update(
                resolve_typescript_import(file_path, edge.module, all_files, aliases)
            )
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


def feature_rule_violations(root: Path, feature: FeatureContext, reverse_graph: dict,
                            rules=PY_LAYER_RULES) -> list:
    violations: list = []
    for rule in rules:
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


# ── per-stack scan legs ───────────────────────────────────────────────────────


def scan_python(root: Path) -> list[dict]:
    """Python leg: emits RULE_CONSUMER (unwired layer files) and RULE_ROOT
    (composition.py missing an existing layer)."""
    features = build_feature_contexts(root, "python")
    if not features:
        return []
    graph = build_python_graph(root)
    reverse = build_reverse_graph(graph)
    violations: list = []
    for feature in features:
        violations.extend(feature_rule_violations(root, feature, reverse, PY_LAYER_RULES))
    for feature in features:
        violations.extend(python_composition_root_violations(root, feature, graph))
    return violations


def scan_typescript_family(root: Path) -> list[dict]:
    """TypeScript + Supabase leg (a single non-python pass — see module PARITY
    NOTE: both stacks share the identical consumer ``layer_rules`` and neither
    runs a composition-root check, so one graph leg realizes both).

    Mirrors legacy ``analyze_typescript_repo``: build the TS import graph
    (relative + tsconfig-alias resolution, value imports / re-exports as edges,
    type-only imports ignored) and emit ONLY RULE_CONSUMER for source-layer files
    with no valid downstream consumer.
    """
    features = build_feature_contexts(root, "typescript")
    if not features:
        return []
    graph = build_typescript_graph(root)
    reverse = build_reverse_graph(graph)
    violations: list = []
    for feature in features:
        violations.extend(feature_rule_violations(root, feature, reverse, TS_LAYER_RULES))
    return violations


# ── public scan API (the v1.1 contract surface) ───────────────────────────────


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one stack ``root`` and return RAW v1.1 violation dicts.

    Discovery root == import root == ``root``. Runs every stack leg the legacy
    oracle covers — python (RULE_CONSUMER + RULE_ROOT) and the TypeScript/Supabase
    family (RULE_CONSUMER) — so the same obligation is enforced across all three
    stacks. A leg whose shape is absent under ``root`` discovers no features and
    contributes nothing.
    """
    root = Path(root)
    violations: list = []
    violations.extend(scan_python(root))
    violations.extend(scan_typescript_family(root))
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
