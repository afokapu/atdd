"""
Test for intra-layer code duplication via AST subtree hashing.

Validates:
- No structurally identical code fragments (>=5 statements) within same layer
- Convention file exists with required configuration

Conventions from:
- atdd/coder/conventions/duplication.convention.yaml

Algorithm: Normalize AST subtrees (strip names/constants), hash consecutive
statement blocks, group by layer, report collisions across different files.
"""

import ast
import hashlib
import os
import fnmatch
import yaml
import pytest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import atdd
from atdd.coach.utils.repo import find_repo_root


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()
PYTHON_DIR = REPO_ROOT / "python"

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
DUPLICATION_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "duplication.convention.yaml"

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".dart_tool",
    "build", ".pub-cache", "dist", ".next", ".nuxt", "coverage",
    ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
}


# ---------------------------------------------------------------------------
# Convention loader
# ---------------------------------------------------------------------------
def load_duplication_convention() -> Dict:
    """Load duplication convention YAML.  Returns empty dict when missing."""
    if not DUPLICATION_CONVENTION.exists():
        return {}
    with open(DUPLICATION_CONVENTION, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
        return data.get("duplication", {})


# ---------------------------------------------------------------------------
# Layer detection (reused from test_python_architecture.py logic)
# ---------------------------------------------------------------------------
def determine_layer_from_path(file_path: Path) -> str:
    """
    Determine architectural layer from file path.

    Returns: 'domain', 'application', 'presentation', 'integration', or 'unknown'
    """
    path_str = str(file_path).lower()

    # Explicit layer directories
    if '/domain/' in path_str or path_str.endswith('/domain.py'):
        return 'domain'
    elif '/application/' in path_str or path_str.endswith('/application.py'):
        return 'application'
    elif '/presentation/' in path_str or path_str.endswith('/presentation.py'):
        return 'presentation'
    elif '/integration/' in path_str or '/infrastructure/' in path_str:
        return 'integration'

    # Alternative patterns
    if '/entities/' in path_str or '/models/' in path_str or '/value_objects/' in path_str:
        return 'domain'
    elif '/use_cases/' in path_str or '/usecases/' in path_str or '/services/' in path_str:
        return 'application'
    elif '/controllers/' in path_str or '/handlers/' in path_str or '/views/' in path_str:
        return 'presentation'
    elif '/adapters/' in path_str or '/repositories/' in path_str or '/gateways/' in path_str:
        return 'integration'

    return 'unknown'


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
def _matches_exclusion(file_path: Path, exclusions: List[str], base_dir: Path) -> bool:
    """Return True if file_path matches any exclusion glob relative to base_dir."""
    try:
        rel = str(file_path.relative_to(base_dir))
    except ValueError:
        rel = str(file_path)
    return any(fnmatch.fnmatch(rel, pat) for pat in exclusions)


def _collect_python_files(
    base_dir: Path,
    exclusions: Optional[List[str]] = None,
) -> List[Path]:
    """Walk base_dir for *.py files, honouring skip-dirs and exclusions."""
    if not base_dir.exists():
        return []
    exclusions = exclusions or []
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(base_dir):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            full = Path(dirpath) / fname
            if _matches_exclusion(full, exclusions, base_dir):
                continue
            files.append(full)
    return files


# ---------------------------------------------------------------------------
# AST normalization + subtree hashing
# ---------------------------------------------------------------------------
class _ASTNormalizer(ast.NodeTransformer):
    """
    Strip variable names and literal values from AST to capture structure only.

    - All Name nodes → Name(id="VAR")
    - All constants → Constant(value=0)
    - All string constants → Constant(value="")
    - Attribute names preserved (method signatures matter)
    """

    def visit_Name(self, node: ast.Name) -> ast.Name:
        self.generic_visit(node)
        return ast.copy_location(ast.Name(id="VAR", ctx=node.ctx), node)

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(value=""), node)
        if isinstance(node.value, (int, float, complex)):
            return ast.copy_location(ast.Constant(value=0), node)
        return node


def _hash_statements(stmts: List[ast.stmt]) -> str:
    """Normalize a list of statements and return a deterministic hash."""
    normalizer = _ASTNormalizer()
    normalized = []
    for stmt in stmts:
        normalized.append(normalizer.visit(ast.parse(ast.unparse(stmt)).body[0]))
    dumped = "\n".join(ast.dump(s) for s in normalized)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:16]


def extract_fragments(
    file_path: Path,
    min_statements: int,
) -> List[Tuple[str, int, int]]:
    """
    Extract hashable code fragments from a Python file.

    Uses a sliding window of min_statements consecutive top-level and
    function-body statements.

    Returns: list of (hash, start_line, end_line)
    """
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    fragments: List[Tuple[str, int, int]] = []

    def _scan_body(body: List[ast.stmt]) -> None:
        """Scan a statement list with a sliding window."""
        if len(body) < min_statements:
            return
        for i in range(len(body) - min_statements + 1):
            window = body[i:i + min_statements]
            try:
                h = _hash_statements(window)
            except Exception:
                continue
            start_line = window[0].lineno
            end_line = window[-1].end_lineno or window[-1].lineno
            fragments.append((h, start_line, end_line))

    # Scan module-level statements
    _scan_body(tree.body)

    # Scan function/method bodies
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _scan_body(node.body)

    return fragments


# ---------------------------------------------------------------------------
# Duplication detection
# ---------------------------------------------------------------------------
def find_intra_layer_duplicates(
    files_by_layer: Dict[str, List[Path]],
    min_statements: int,
) -> List[Dict]:
    """
    Find duplicate code fragments within the same architectural layer.

    Only reports duplicates across DIFFERENT files (same-file duplication
    is less concerning and often intentional).

    Returns: list of violation dicts with file, line, detail.
    """
    violations: List[Dict] = []

    for layer, files in files_by_layer.items():
        if len(files) < 2:
            continue

        # hash → [(file, start_line, end_line)]
        hash_map: Dict[str, List[Tuple[Path, int, int]]] = {}

        for f in files:
            for h, start, end in extract_fragments(f, min_statements):
                hash_map.setdefault(h, []).append((f, start, end))

        # Report fragments that appear in more than one file
        for h, locations in hash_map.items():
            unique_files = set(loc[0] for loc in locations)
            if len(unique_files) < 2:
                continue

            # Group by file for cleaner reporting
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
                    "statements": min_statements,
                })

    return violations


def _rel_path(file_path: Path) -> Path:
    """Get relative path from REPO_ROOT."""
    try:
        return file_path.relative_to(REPO_ROOT)
    except ValueError:
        return file_path


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.coder
def test_duplication_convention_exists():
    """
    SPEC-CODER-DUP-CONV: Duplication convention YAML exists and defines rules.

    Given: Convention file at src/atdd/coder/conventions/duplication.convention.yaml
    When: Loading and parsing the convention YAML
    Then: Convention defines intra_layer_duplication rule with required config

    Convention: atdd/coder/conventions/duplication.convention.yaml
    """
    assert DUPLICATION_CONVENTION.exists(), (
        f"duplication.convention.yaml must exist at {DUPLICATION_CONVENTION}"
    )

    convention = load_duplication_convention()
    rules = convention.get("rules", {})
    assert "intra_layer_duplication" in rules, (
        "Convention must define 'intra_layer_duplication' rule"
    )

    rule = rules["intra_layer_duplication"]
    assert "min_fragment_statements" in rule, "Rule must define min_fragment_statements"
    assert "layers" in rule, "Rule must define layers to check"
    assert rule["min_fragment_statements"] >= 3, (
        "min_fragment_statements must be >= 3 to avoid trivial matches"
    )


@pytest.mark.coder
def test_no_intra_layer_duplication():
    """
    SPEC-CODER-DUP-0001: No structurally identical fragments within same layer.

    AST subtree hashing detects copy-paste code across different files in
    the same architectural layer.  Variable names and literals are normalized
    so renamed copies are still caught.

    Given: Python files in python/ grouped by architectural layer
    When: Extracting statement fragments and comparing hashes within each layer
    Then: No duplicate fragments found across different files

    Convention: atdd/coder/conventions/duplication.convention.yaml (DUP-0001)
    """
    convention = load_duplication_convention()
    rule = convention.get("rules", {}).get("intra_layer_duplication", {})
    min_stmts = rule.get("min_fragment_statements", 5)
    exclusions = rule.get("exclusions", [])

    files = _collect_python_files(PYTHON_DIR, exclusions)
    if not files:
        pytest.skip("No Python files found in python/ to validate")

    # Group files by layer
    files_by_layer: Dict[str, List[Path]] = {}
    for f in files:
        layer = determine_layer_from_path(f)
        if layer == "unknown":
            continue
        files_by_layer.setdefault(layer, []).append(f)

    violations = find_intra_layer_duplicates(files_by_layer, min_stmts)

    if violations:
        lines = []
        for v in violations[:10]:
            rel_a = _rel_path(v["file_a"])
            rel_b = _rel_path(v["file_b"])
            lines.append(
                f"[{v['layer']}] {rel_a}:{v['line_a']} ↔ {rel_b}:{v['line_b']} "
                f"({v['statements']} identical statements)"
            )

        pytest.fail(
            f"\n\nFound {len(violations)} intra-layer duplication(s):\n\n"
            + "\n".join(lines)
            + (
                f"\n\n... and {len(violations) - 10} more"
                if len(violations) > 10
                else ""
            )
            + "\n\nExtract shared logic into a common module within the layer."
            + "\nSee: atdd/coder/conventions/duplication.convention.yaml (DUP-0001)"
        )
