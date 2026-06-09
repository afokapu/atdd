"""
Validate intra-feature composition completeness for Python and TypeScript stacks.

Scope:
- Intra-feature composition only
- Existing-layer-only validation to avoid false positives on partial features
- TypeScript value imports and barrel re-exports count as composition evidence
- Python composition.py reachability respects setter-call wiring for presentation

Convention: src/atdd/coder/conventions/composition.convention.yaml

Structured violations (issue #394): emits canonical ``Violation`` records keyed
off ``REFACTOR-COMPOSITION-CONSUMER-001`` (layer file unwired) and
``REFACTOR-COMPOSITION-ROOT-001`` (composition root incomplete) declared in
``src/atdd/coder/conventions/refactor.convention.yaml``. The private
``CompositionViolation`` dataclass was removed; spec_ids 0001/0002/0003 are
preserved as a `spec_id=...` token in ``Violation.detail`` for greppability.
"""

from __future__ import annotations

import ast
import json
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import atdd
import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.coder.utils.python_file_walker import walk_consumer_python_files
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coder.validators._toolkit_roots import ScanRoot, is_excluded_fixture


# Rule bindings — fail at import if conventions drift (issue #394).
_RULE_CONSUMER = bind_rule("coder.refactor.composition-consumer")
_RULE_ROOT = bind_rule("coder.refactor.composition-root")


REPO_ROOT = find_repo_root()
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
COMPOSITION_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "composition.convention.yaml"
BOUNDARIES_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "boundaries.convention.yaml"
GREEN_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "green.convention.yaml"
FRONTEND_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "frontend.convention.yaml"
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "composition_completeness"

LAYER_NAMES = ("domain", "application", "integration", "presentation")
TS_CONNECTOR_FILES = {"index.ts", "index.tsx", "types.ts"}
PY_CONNECTOR_FILES = {"__init__.py"}
TEST_FILE_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts")
TS_FILE_SUFFIXES = (".ts", ".tsx")


@dataclass(frozen=True)
class FeatureContext:
    stack: str
    repo_root: Path
    stack_root: Path
    feature_dir: Path
    layer_files: Dict[str, List[Path]]
    root_files: List[Path]

    @property
    def feature_id(self) -> str:
        return str(self.feature_dir.relative_to(self.stack_root))


# CompositionViolation removed in #394 — replaced with canonical Violation.
# Domain-specific fields (spec_id, feature, file, layer, expected, found) are
# encoded into ``Violation.location`` and ``Violation.detail`` so downstream
# tooling and tests can still recover them by parsing the canonical record.


@dataclass(frozen=True)
class TypeScriptEdge:
    module: str
    is_type_only: bool
    is_reexport: bool


@dataclass(frozen=True)
class PythonImportRef:
    module: str
    names: Tuple[str, ...]
    level: int


def load_yaml(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def build_reverse_graph(graph: Dict[Path, Set[Path]]) -> Dict[Path, Set[Path]]:
    reverse: Dict[Path, Set[Path]] = {node: set() for node in graph}
    for source, targets in graph.items():
        for target in targets:
            reverse.setdefault(target, set()).add(source)
    return reverse


def bfs(start_nodes: Iterable[Path], graph: Dict[Path, Set[Path]]) -> Set[Path]:
    visited: Set[Path] = set()
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
    if path.name in TS_CONNECTOR_FILES or path.name in PY_CONNECTOR_FILES:
        return False
    return True


def detect_layer(path: Path) -> str:
    name = path.name
    if name in {"composition.py", "wagon.py"}:
        return "composition"
    if name == "index.ts" and "supabase" in path.parts and "functions" in path.parts:
        return "composition"
    for layer in LAYER_NAMES:
        if layer in path.parts:
            return layer
    return "unknown"


def feature_layer_root(feature_dir: Path, stack: str) -> Path:
    return feature_dir / "src" if stack == "python" else feature_dir


def feature_dir_for_layer_dir(layer_dir: Path, stack: str) -> Optional[Path]:
    if stack == "python":
        if layer_dir.parent.name != "src":
            return None
        return layer_dir.parent.parent

    return layer_dir.parent


def find_feature_dirs(stack_root: Path, stack: str) -> Set[Path]:
    feature_dirs: Set[Path] = set()
    if not stack_root.exists():
        return feature_dirs

    # Skip negative fixtures only when the scanned root is a real tree — the
    # fixture dogfood tests intentionally root the analyzer inside fixtures (#958).
    skip_fixtures = not is_excluded_fixture(stack_root)

    for layer in LAYER_NAMES:
        for layer_dir in stack_root.rglob(layer):
            if not layer_dir.is_dir():
                continue
            feature_dir = feature_dir_for_layer_dir(layer_dir, stack)
            if feature_dir is None or feature_dir == stack_root:
                continue
            # Negative fixtures self-trigger — never discover them as features (#958).
            if skip_fixtures and is_excluded_fixture(feature_dir):
                continue
            feature_dirs.add(feature_dir)

    return feature_dirs


def root_files_for_feature(feature_dir: Path, stack: str) -> List[Path]:
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

    roots = []
    presentation_dir = feature_dir / "presentation"
    if presentation_dir.exists():
        roots.extend(sorted(presentation_dir.glob("*Page.tsx")))
        roots.extend(sorted(presentation_dir.glob("*Container.tsx")))
    return roots


def build_feature_contexts(repo_root: Path, stack: str, stack_root: Path) -> List[FeatureContext]:
    contexts: List[FeatureContext] = []
    for feature_dir in sorted(find_feature_dirs(stack_root, stack)):
        layer_files: Dict[str, List[Path]] = {}
        layer_root = feature_layer_root(feature_dir, stack)
        for layer in LAYER_NAMES:
            files: List[Path] = []
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

        contexts.append(
            FeatureContext(
                stack=stack,
                repo_root=repo_root,
                stack_root=stack_root,
                feature_dir=feature_dir,
                layer_files=layer_files,
                root_files=root_files_for_feature(feature_dir, stack),
            )
        )

    return contexts


def collect_python_files(
    repo_root: Path, discovery_root: Optional[Path] = None
) -> List[Path]:
    """Collect python source files under the discovery root.

    ``discovery_root`` defaults to the consumer ``python/`` tree (back-compat).
    When a toolkit discovery root (``src/atdd``) is supplied, the negative
    fixtures under ``coder/validators/fixtures/`` are excluded so they cannot
    self-trigger (#958).
    """
    root = discovery_root if discovery_root is not None else (repo_root / "python")
    if not root.exists():
        return []
    # Exclude the negative fixtures only when scanning a real tree — fixture-based
    # dogfood tests deliberately point the analyzer AT a fixture subtree (#958).
    skip_fixtures = not is_excluded_fixture(root)
    return sorted(
        path
        for path in walk_consumer_python_files(root)
        if not graph_file_excluded(path)
        and not (skip_fixtures and is_excluded_fixture(path))
    )


def collect_typescript_files(repo_root: Path, stack: str) -> List[Path]:
    if stack == "supabase":
        stack_root = repo_root / "supabase" / "functions"
    else:
        stack_root = repo_root / "web"

    if not stack_root.exists():
        return []

    files: List[Path] = []
    for suffix in TS_FILE_SUFFIXES:
        files.extend(stack_root.rglob(f"*{suffix}"))

    return sorted(path for path in files if path.is_file() and not graph_file_excluded(path))


def find_python_feature_root(file_path: Path) -> Optional[Path]:
    if file_path.name in {"composition.py", "wagon.py"} and (file_path.parent / "src").exists():
        return file_path.parent

    current = file_path.parent
    while current != current.parent:
        if current.name == "src":
            return current.parent
        current = current.parent

    return None


def candidate_python_paths(base_path: Path, all_files: Set[Path]) -> Set[Path]:
    candidates: Set[Path] = set()

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


def resolve_python_import(
    source_file: Path,
    import_ref: PythonImportRef,
    all_files: Set[Path],
    repo_root: Path,
    import_root: Optional[Path] = None,
) -> Set[Path]:
    """Resolve a python import to candidate target files.

    ``import_root`` is the directory a dotted import resolves against on disk. It
    defaults to the consumer ``python/`` base (back-compat); the toolkit passes
    ``src`` so a qualified ``atdd.<wagon>.<feature>.src.<layer>`` import resolves
    to ``src/atdd/<wagon>/<feature>/src/<layer>`` instead of failing against a
    ``python`` base (the #955 false-violation fix — #958).
    """
    candidates: Set[Path] = set()
    base_root = import_root if import_root is not None else (repo_root / "python")

    if import_ref.level > 0:
        base_dir = source_file.parent
        for _ in range(import_ref.level - 1):
            base_dir = base_dir.parent
        relative_base = base_dir / import_ref.module.replace(".", "/") if import_ref.module else base_dir
        candidates.update(candidate_python_paths(relative_base, all_files))

    if import_ref.module:
        top_level = import_ref.module.split(".", 1)[0]
        feature_root = find_python_feature_root(source_file)
        if feature_root and top_level in LAYER_NAMES:
            local_base = feature_root / "src" / import_ref.module.replace(".", "/")
            candidates.update(candidate_python_paths(local_base, all_files))

        repo_base = base_root / import_ref.module.replace(".", "/")
        candidates.update(candidate_python_paths(repo_base, all_files))

    return candidates


def extract_python_imports(file_path: Path) -> List[PythonImportRef]:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    refs: List[PythonImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                refs.append(PythonImportRef(module=alias.name, names=(alias.asname or alias.name,), level=0))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = tuple(alias.asname or alias.name for alias in node.names)
            refs.append(PythonImportRef(module=module, names=names, level=node.level))

    return refs


def extract_called_names(file_path: Path) -> Set[str]:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()

    called: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
    return called


def build_python_graph(
    repo_root: Path,
    discovery_root: Optional[Path] = None,
    import_root: Optional[Path] = None,
) -> Dict[Path, Set[Path]]:
    python_files = collect_python_files(repo_root, discovery_root)
    all_files = set(python_files)
    graph: Dict[Path, Set[Path]] = {file_path: set() for file_path in python_files}

    for file_path in python_files:
        called_names = extract_called_names(file_path) if file_path.name == "composition.py" else set()
        for import_ref in extract_python_imports(file_path):
            resolved = resolve_python_import(
                file_path, import_ref, all_files, repo_root, import_root=import_root
            )

            if file_path.name == "composition.py" and import_ref.names:
                setter_only = all(name.startswith("set_") for name in import_ref.names)
                if setter_only:
                    resolved = {
                        target for target in resolved
                        if detect_layer(target) != "presentation" or any(name in called_names for name in import_ref.names)
                    }

            graph[file_path].update(resolved)

    return graph


def typescript_edges(file_path: Path) -> List[TypeScriptEdge]:
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return []

    statements = re.findall(r"(?:^|\n)\s*(?:import|export)[\s\S]*?;", content)
    edges: List[TypeScriptEdge] = []

    for statement in statements:
        module_match = re.search(r"from\s+['\"]([^'\"]+)['\"]", statement)
        if not module_match:
            continue
        stripped = statement.strip()
        edges.append(
            TypeScriptEdge(
                module=module_match.group(1),
                is_type_only=stripped.startswith("import type") or stripped.startswith("export type"),
                is_reexport=stripped.startswith("export"),
            )
        )

    return edges


def load_tsconfig_paths(repo_root: Path) -> List[Tuple[str, List[str], Path]]:
    tsconfig_path = repo_root / "tsconfig.json"
    if not tsconfig_path.exists():
        return []

    try:
        data = json.loads(tsconfig_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    compiler_options = data.get("compilerOptions", {})
    base_url = compiler_options.get("baseUrl", ".")
    base_dir = (repo_root / base_url).resolve()
    path_map = compiler_options.get("paths", {})

    aliases: List[Tuple[str, List[str], Path]] = []
    for alias, targets in path_map.items():
        if isinstance(targets, list):
            aliases.append((alias, [str(target) for target in targets], base_dir))
    return aliases


def match_alias(alias: str, module: str) -> Optional[str]:
    if "*" not in alias:
        return "" if module == alias else None

    prefix, suffix = alias.split("*", 1)
    if not module.startswith(prefix):
        return None
    if suffix and not module.endswith(suffix):
        return None

    end = len(module) - len(suffix) if suffix else len(module)
    return module[len(prefix):end]


def candidate_typescript_paths(base_path: Path, all_files: Set[Path]) -> Set[Path]:
    candidates: Set[Path] = set()

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


def resolve_typescript_import(
    source_file: Path,
    module: str,
    repo_root: Path,
    all_files: Set[Path],
    aliases: Sequence[Tuple[str, List[str], Path]],
) -> Set[Path]:
    if module.startswith("."):
        return candidate_typescript_paths((source_file.parent / module).resolve(), all_files)

    for alias, targets, base_dir in aliases:
        wildcard = match_alias(alias, module)
        if wildcard is None:
            continue
        resolved: Set[Path] = set()
        for target in targets:
            target_path = target.replace("*", wildcard)
            resolved.update(candidate_typescript_paths((base_dir / target_path).resolve(), all_files))
        if resolved:
            return resolved

    return set()


def build_typescript_graph(repo_root: Path, stack: str) -> Dict[Path, Set[Path]]:
    ts_files = collect_typescript_files(repo_root, stack)
    all_files = set(ts_files)
    aliases = load_tsconfig_paths(repo_root)
    graph: Dict[Path, Set[Path]] = {file_path: set() for file_path in ts_files}

    for file_path in ts_files:
        for edge in typescript_edges(file_path):
            if edge.is_type_only:
                continue
            graph[file_path].update(resolve_typescript_import(file_path, edge.module, repo_root, all_files, aliases))

    return graph


def valid_upstream_consumers(
    target_file: Path,
    reverse_graph: Dict[Path, Set[Path]],
    allowed_layers: Set[str],
) -> Set[Path]:
    upstream = bfs(reverse_graph.get(target_file, set()), reverse_graph)
    return {path for path in upstream if detect_layer(path) in allowed_layers}


def local_consumer_candidates(feature: FeatureContext, allowed_layers: Set[str]) -> Set[Path]:
    candidates: Set[Path] = set()
    for layer in allowed_layers:
        if layer == "composition":
            candidates.update(feature.root_files)
            continue
        candidates.update(feature.layer_files.get(layer, []))
    return candidates


def feature_rule_violations(
    feature: FeatureContext,
    reverse_graph: Dict[Path, Set[Path]],
    rules: Sequence[Dict[str, object]],
) -> List[Violation]:
    violations: List[Violation] = []

    for rule in rules:
        spec_id = str(rule["spec_id"])
        source_layer = str(rule["source_layer"])
        allowed_layers = set(rule["consumer_layers"])

        for source_file in feature.layer_files.get(source_layer, []):
            if not candidate_source_file(source_file):
                continue

            consumers = valid_upstream_consumers(source_file, reverse_graph, allowed_layers)
            if consumers:
                continue

            if not local_consumer_candidates(feature, allowed_layers):
                continue

            consumer_desc = " or ".join(sorted(allowed_layers))
            file_rel = str(source_file.relative_to(feature.feature_dir))
            violations.append(Violation(
                rule_id=_RULE_CONSUMER.rule_id,
                severity=_RULE_CONSUMER.severity,
                location=f"{feature.feature_id}/{file_rel}",
                detail=(
                    f"spec_id={spec_id} layer={source_layer} "
                    f"expected=imported_by_{consumer_desc.replace(' ', '_')} "
                    f"found=0_consumers — this {source_layer} file exists but "
                    f"is never consumed; add a valid downstream consumer or "
                    f"remove it"
                ),
                fix_hint_ref=_RULE_CONSUMER.fix_hint_ref,
            ))

    return violations


def python_composition_root_violations(
    feature: FeatureContext,
    graph: Dict[Path, Set[Path]],
    rule: Dict[str, object],
) -> List[Violation]:
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
    return [Violation(
        rule_id=_RULE_ROOT.rule_id,
        severity=_RULE_ROOT.severity,
        location=f"{feature.feature_id}/{file_rel}",
        detail=(
            f"spec_id={rule['spec_id']} layer=composition "
            f"expected=reaches_all_existing_layers "
            f"found=missing_{','.join(missing)} — the feature composition "
            f"root does not reach every existing layer; import the missing "
            f"layer directly or wire it through a called setter"
        ),
        fix_hint_ref=_RULE_ROOT.fix_hint_ref,
    )]


def analyze_python_repo(repo_root: Path) -> List[Violation]:
    convention = load_yaml(COMPOSITION_CONVENTION)
    stack_conf = convention["composition"]["stacks"]["python"]
    stack_root = repo_root / stack_conf["repo_root"]
    features = build_feature_contexts(repo_root, "python", stack_root)
    if not features:
        return []

    graph = build_python_graph(repo_root)
    reverse = build_reverse_graph(graph)
    violations: List[Violation] = []

    violations.extend(
        violation
        for feature in features
        for violation in feature_rule_violations(feature, reverse, stack_conf["layer_rules"])
    )
    violations.extend(
        violation
        for feature in features
        for violation in python_composition_root_violations(feature, graph, stack_conf["composition_root_rule"])
    )
    return violations


def analyze_python_root(repo_root: Path, scan_root: ScanRoot) -> List[Violation]:
    """Analyze python composition completeness for one config-driven scan root.

    Generalizes :func:`analyze_python_repo` (which is pinned to the consumer
    ``python/`` tree) to any ``ScanRoot``: feature contexts are discovered under
    ``scan_root.discovery_root`` and the import graph resolves against
    ``scan_root.import_root`` — so the toolkit's own four-tier features under
    ``src/atdd`` are analyzed with their qualified ``atdd.`` imports resolving
    correctly (#958). Returns the canonical Violation records (unsorted); the
    ratchet decides which are new vs grandfathered.
    """
    features = build_feature_contexts(repo_root, "python", scan_root.discovery_root)
    if not features:
        return []

    graph = build_python_graph(
        repo_root,
        discovery_root=scan_root.discovery_root,
        import_root=scan_root.import_root,
    )
    reverse = build_reverse_graph(graph)

    convention = load_yaml(COMPOSITION_CONVENTION)
    stack_conf = convention["composition"]["stacks"]["python"]

    violations: List[Violation] = []
    violations.extend(
        violation
        for feature in features
        for violation in feature_rule_violations(feature, reverse, stack_conf["layer_rules"])
    )
    violations.extend(
        violation
        for feature in features
        for violation in python_composition_root_violations(feature, graph, stack_conf["composition_root_rule"])
    )
    return violations


def analyze_typescript_repo(repo_root: Path, stack: str = "typescript") -> List[Violation]:
    convention = load_yaml(COMPOSITION_CONVENTION)
    stack_conf = convention["composition"]["stacks"][stack]
    stack_root = repo_root / stack_conf["repo_root"]
    features = build_feature_contexts(repo_root, stack, stack_root)
    if not features:
        return []

    graph = build_typescript_graph(repo_root, stack)
    reverse = build_reverse_graph(graph)

    return [
        violation
        for feature in features
        for violation in feature_rule_violations(feature, reverse, stack_conf["layer_rules"])
    ]


def format_violation(violation: Violation) -> str:
    """Render a Violation for the assert_no_violations error message."""
    return f"{violation.rule_id} FAIL: {violation.location}\n  {violation.detail}"


def assert_no_violations(violations: Sequence[Violation]) -> None:
    assert not violations, "\n\n" + "\n\n".join(format_violation(item) for item in violations)


@pytest.mark.coder
def test_composition_convention_exists_and_has_required_sections():
    """
    SPEC-CODER-COMP-0007: Composition convention exists with stack, rule, and exclusion sections.

    Given: The coder conventions package
    When: Loading composition.convention.yaml
    Then: The file exists and defines stacks, rules, and exclusions
    """
    assert COMPOSITION_CONVENTION.exists(), "composition.convention.yaml must exist"

    convention = load_yaml(COMPOSITION_CONVENTION)
    assert "composition" in convention, "composition convention must define a composition section"
    assert "rules" in convention, "composition convention must define rules"
    assert "exclusions" in convention, "composition convention must define exclusions"
    assert {"typescript", "python", "supabase"} <= set(convention["composition"]["stacks"]), \
        "composition convention must define typescript, python, and supabase stacks"


@pytest.mark.coder
def test_existing_conventions_reference_composition_rules():
    """
    SPEC-CODER-COMP-0008: Existing coder conventions cross-reference composition completeness rules.

    Given: Boundaries, green, and frontend conventions
    When: Reading their composition-related sections
    Then: Each convention references composition.convention.yaml
    """
    boundaries = load_yaml(BOUNDARIES_CONVENTION)
    green = load_yaml(GREEN_CONVENTION)
    frontend = load_yaml(FRONTEND_CONVENTION)

    assert "composition_completeness" in boundaries["interaction"]["composition_roots"], \
        "boundaries.convention.yaml must reference composition completeness"
    assert green["green_phase"]["composition_root"]["composition_completeness"]["convention"] == \
        "composition.convention.yaml"
    assert frontend["frontend"]["structure"]["preact"]["composition_completeness"]["convention"] == \
        "composition.convention.yaml"


@pytest.mark.coder
def test_composition_completeness_python_fixture_passes_for_complete_and_partial_features():
    """
    SPEC-CODER-COMP-0004: Python composition completeness passes for complete and partial features.

    Given: A fixture repo with complete and intentionally partial Python features
    When: Analyzing composition completeness
    Then: No violations are reported
    """
    if not is_atdd_source_repo():
        pytest.skip("fixture-based dogfood test — runs only inside the atdd source repo (#276)")
    violations = analyze_python_repo(FIXTURE_ROOT / "python_pass")
    assert_no_violations(violations)


@pytest.mark.coder
def test_composition_completeness_python_fixture_detects_missing_setter_call():
    """
    SPEC-CODER-COMP-0004: Presentation setter imports only count when called from composition.py.

    Given: A Python fixture with setter imports but no setter call
    When: Analyzing composition completeness
    Then: The composition root is reported as missing presentation reachability
    """
    if not is_atdd_source_repo():
        pytest.skip("fixture-based dogfood test — runs only inside the atdd source repo (#276)")
    violations = analyze_python_repo(FIXTURE_ROOT / "python_fail_setter")
    assert len(violations) == 1, "expected one composition root violation"
    violation = violations[0]
    assert violation.rule_id == "coder.refactor.composition-root"
    assert "spec_id=SPEC-CODER-COMP-0004" in violation.detail
    assert violation.location.startswith("bad_match/orchestrate_bad/")
    assert "presentation" in violation.detail


@pytest.mark.coder
def test_composition_completeness_typescript_fixture_detects_cameo_and_import_type_gaps():
    """
    SPEC-CODER-COMP-0001: TypeScript detects unwired hooks while ignoring type-only imports.

    Given: A fixture repo with a Cameo-style gap and a type-only hook import
    When: Analyzing composition completeness
    Then: Application layer violations are reported for both unwired hooks
    """
    if not is_atdd_source_repo():
        pytest.skip("fixture-based dogfood test — runs only inside the atdd source repo (#276)")
    violations = analyze_typescript_repo(FIXTURE_ROOT / "typescript_repo")
    # Violation.location is "feature_id/file_path" — split on the last '/'
    # before "application/" to recover the feature/file pair.
    violation_map = {item.location: item for item in violations}

    cameo_loc = "manage-profile/display-profile/application/useCameoBalance.ts"
    forecast_loc = "arena/show-forecast/application/useForecast.ts"
    assert cameo_loc in violation_map
    assert forecast_loc in violation_map

    cameo = violation_map[cameo_loc]
    forecast = violation_map[forecast_loc]

    assert cameo.rule_id == "coder.refactor.composition-consumer"
    assert forecast.rule_id == "coder.refactor.composition-consumer"
    assert "spec_id=SPEC-CODER-COMP-0001" in cameo.detail
    assert "spec_id=SPEC-CODER-COMP-0001" in forecast.detail


@pytest.mark.coder
def test_composition_completeness_typescript_fixture_accepts_barrels_and_partial_features():
    """
    SPEC-CODER-COMP-0006: Barrel re-exports count as edges and partial features do not over-fail.

    Given: A fixture repo with barrel-mediated foreign consumption and a partial feature
    When: Analyzing composition completeness
    Then: Barrel-consumed hooks pass and partial-feature integration is skipped
    """
    if not is_atdd_source_repo():
        pytest.skip("fixture-based dogfood test — runs only inside the atdd source repo (#276)")
    violations = analyze_typescript_repo(FIXTURE_ROOT / "typescript_repo")
    violated_locations = {item.location for item in violations}

    assert not any(loc.endswith("application/usePlayerRank.ts") for loc in violated_locations)
    assert not any(loc.endswith("integration/EloRepository.ts") for loc in violated_locations)


@pytest.mark.coder
def test_composition_completeness_python_live_repo():
    """
    SPEC-CODER-COMP-0004: Real Python consumer repos have complete composition wiring.

    Given: The consumer repository python/ tree
    When: Analyzing Python composition completeness
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    if not build_feature_contexts(REPO_ROOT, "python", REPO_ROOT / "python"):
        pytest.skip("No Python feature tree found in python/ to validate")

    violations = analyze_python_repo(REPO_ROOT)
    assert_disposition_satisfied(
        validator_id="composition_completeness_python",
        violations=violations,
    )


@pytest.mark.coder
def test_composition_completeness_typescript_live_repo():
    """
    SPEC-CODER-COMP-0001: Real web consumer repos have complete TypeScript composition wiring.

    Given: The consumer repository web/src tree
    When: Analyzing TypeScript composition completeness
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    if not build_feature_contexts(REPO_ROOT, "typescript", REPO_ROOT / "web" / "src"):
        pytest.skip("No web/src feature tree found to validate")

    violations = analyze_typescript_repo(REPO_ROOT)
    assert_disposition_satisfied(
        validator_id="composition_completeness_typescript",
        violations=violations,
    )


@pytest.mark.coder
def test_composition_completeness_supabase_live_repo():
    """
    SPEC-CODER-COMP-0002: Real Supabase consumer repos have complete composition wiring.

    Given: The consumer repository supabase/functions tree
    When: Analyzing Supabase composition completeness
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    if not build_feature_contexts(REPO_ROOT, "supabase", REPO_ROOT / "supabase" / "functions"):
        pytest.skip("No supabase/functions feature tree found to validate")

    violations = analyze_typescript_repo(REPO_ROOT, stack="supabase")
    assert_disposition_satisfied(
        validator_id="composition_completeness_supabase",
        violations=violations,
    )
