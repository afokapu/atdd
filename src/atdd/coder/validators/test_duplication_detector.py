"""
Test for intra-layer code duplication via AST subtree hashing.

Validates:
- No structurally identical code fragments (>=5 statements) within same layer
- Convention file exists with required configuration

Conventions from:
- atdd/coder/conventions/duplication.convention.yaml

Algorithm: Normalize AST subtrees (strip names/constants), hash consecutive
statement blocks, group by layer, report collisions across different files.

Structured violations (issue #394): emits ``Violation`` records keyed off
``DUPLICATION-PY-001`` declared in
``src/atdd/coder/conventions/duplication.convention.yaml``.
"""

import ast
import hashlib
import fnmatch
import yaml
import pytest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import resolve_code_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.coder.utils.python_file_walker import walk_consumer_python_files
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied


# Rule bindings — fail at import if conventions drift (issue #394).
_RULE_DUP_PY = bind_rule("coder.duplication.no-intra-layer-code-python")


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()
PYTHON_DIR = resolve_code_root("python", REPO_ROOT)

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
DUPLICATION_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "duplication.convention.yaml"

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
    """Walk base_dir for *.py files, honouring project exclusions.

    Vendored/virtualenv/build directory skipping is handled by the shared
    :func:`walk_consumer_python_files` walker; the per-file exclusion globs
    from the duplication convention are applied on top.
    """
    if not base_dir.exists():
        return []
    exclusions = exclusions or []
    files: List[Path] = []
    for full in walk_consumer_python_files(base_dir):
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


def _is_module_docstring(stmt: ast.stmt) -> bool:
    """True if stmt is a bare string expression (a module/leading docstring)."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _is_import(stmt: ast.stmt) -> bool:
    """True if stmt is an ``import`` or ``from ... import`` (incl. __future__)."""
    return isinstance(stmt, (ast.Import, ast.ImportFrom))


def _is_module_constant(stmt: ast.stmt) -> bool:
    """True if stmt is a module-level constant binding (``X = ...`` / ``X: T = ...``).

    Leading bindings (path constants, ``_RULE = bind_rule(...)``, sentinel
    tuples, etc.) are part of the standard file header, not duplicated logic.
    """
    return isinstance(stmt, (ast.Assign, ast.AnnAssign))


def strip_module_header(body: List[ast.stmt]) -> List[ast.stmt]:
    """Drop the contiguous *leading* header-boilerplate prefix of a module body.

    Issue #960: the strict intra-layer duplication detector counted standard
    file-header boilerplate — the module docstring, ``from __future__`` /
    ``import`` block, and leading module constants — as duplication. Two small
    value-object files in the same layer collided on their headers alone, with
    no real shared logic.

    The boundary: we strip the leading docstring followed by a contiguous run of
    import statements and module-level constant bindings, stopping at the first
    statement of real logic (a function/class definition, control flow, an
    expression call, etc.). Header statements that follow real code are NOT
    stripped, so genuine duplicated logic is still compared and flagged.
    """
    idx = 0
    n = len(body)
    if idx < n and _is_module_docstring(body[idx]):
        idx += 1
    while idx < n and (_is_import(body[idx]) or _is_module_constant(body[idx])):
        idx += 1
    return body[idx:]


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

    # Scan module-level statements, excluding standard header boilerplate
    # (docstring + import block + leading constants) — issue #960.
    _scan_body(strip_module_header(tree.body))

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


def scan_python_duplications(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for intra-layer Python duplications. Used by ratchet baseline."""
    convention = load_duplication_convention()
    rule = convention.get("rules", {}).get("intra_layer_duplication", {})
    min_stmts = rule.get("min_fragment_statements", 5)
    exclusions = rule.get("exclusions", [])
    scan_dirs = rule.get("scan_dirs", ["python/"])

    files: List[Path] = []
    for rel_dir in scan_dirs:
        files.extend(_collect_python_files(repo_root / rel_dir, exclusions))
    if not files:
        return 0, []

    files_by_layer: Dict[str, List[Path]] = {}
    for f in files:
        layer = determine_layer_from_path(f)
        if layer == "unknown":
            continue
        files_by_layer.setdefault(layer, []).append(f)

    raw_violations = find_intra_layer_duplicates(files_by_layer, min_stmts)
    structured: List[Violation] = []
    for v in raw_violations:
        try:
            rel_a = v["file_a"].relative_to(repo_root)
        except ValueError:
            rel_a = v["file_a"]
        try:
            rel_b = v["file_b"].relative_to(repo_root)
        except ValueError:
            rel_b = v["file_b"]
        structured.append(Violation(
            rule_id=_RULE_DUP_PY.rule_id,
            severity=_RULE_DUP_PY.severity,
            location=f"{rel_a}:{v['line_a']}",
            detail=(
                f"[{v['layer']}] {rel_a}:{v['line_a']} <-> {rel_b}:{v['line_b']} "
                f"({v['statements']} identical statements)"
            ),
            fix_hint_ref=_RULE_DUP_PY.fix_hint_ref,
        ))
    return len(structured), structured


@pytest.mark.coder
def test_no_intra_layer_duplication():
    """
    SPEC-CODER-DUP-0001: No structurally identical fragments within same layer.

    AST subtree hashing detects copy-paste code across different files in
    the same architectural layer.  Variable names and literals are normalized
    so renamed copies are still caught.

    Given: Python files in configured scan_dirs grouped by architectural layer
    When: Extracting statement fragments and comparing hashes within each layer
    Then: Violation count does not exceed baseline (ratchet pattern)

    Convention: atdd/coder/conventions/duplication.convention.yaml (DUP-0001)
    """
    count, violations = scan_python_duplications(REPO_ROOT)
    if count == 0 and not violations:
        # Check if there were any files to scan
        convention = load_duplication_convention()
        rule = convention.get("rules", {}).get("intra_layer_duplication", {})
        scan_dirs = rule.get("scan_dirs", ["python/"])
        has_files = any((REPO_ROOT / d).exists() for d in scan_dirs)
        if not has_files:
            pytest.skip("No Python files found in scan_dirs to validate")

    assert_disposition_satisfied(
        validator_id="duplication_detector",
        violations=violations,
    )


# ---------------------------------------------------------------------------
# Issue #960 — header boilerplate must NOT count as duplication
# ---------------------------------------------------------------------------
# Standard 4-line header (docstring + __future__ + 2 imports) followed by a
# leading constant binding (``_RULE = bind_rule("...")``). This is the exact
# 5-statement window that #955 flagged across two value-object files.
_SHARED_HEADER = '''"""{title} value object (pure)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_RULE = bind_rule("coder.duplication.no-intra-layer-code-python")
'''


def _write_domain_file(base: Path, name: str, body: str) -> Path:
    """Write a file under a ``.../domain/`` path so it classifies as 'domain'."""
    domain_dir = base / name / "src" / "domain"
    domain_dir.mkdir(parents=True, exist_ok=True)
    target = domain_dir / f"{name}.py"
    target.write_text(body, encoding="utf-8")
    return target


@pytest.mark.coder
def test_header_boilerplate_only_overlap_is_not_flagged(tmp_path):
    """
    SPEC-CODER-DUP-0960: Two same-layer files sharing ONLY the standard header
    boilerplate (docstring + __future__ + imports + a leading constant) and
    having distinct real bodies must NOT be flagged as intra-layer duplication.

    Reproduces #955: apply_decision/.../domain/record.py vs
    mediate_decision/.../domain/verdict.py collided on header alone.
    """
    file_a = _write_domain_file(tmp_path, "record", _SHARED_HEADER.format(title="DecisionRecord") + '''

@dataclass(frozen=True)
class DecisionRecord:
    record_id: str
    request_id: str

    def to_contract(self) -> dict:
        out: dict = {}
        out["record_id"] = self.record_id
        return out
''')
    file_b = _write_domain_file(tmp_path, "verdict", _SHARED_HEADER.format(title="Verdict") + '''

@dataclass(frozen=True)
class Verdict:
    verdict_id: str
    decided_at: str
    reason: Optional[str] = None

    def is_final(self) -> bool:
        flag = self.reason is not None
        return flag
''')

    violations = find_intra_layer_duplicates({"domain": [file_a, file_b]}, 5)

    assert violations == [], (
        "Files sharing only standard header boilerplate must not be flagged "
        f"as duplication, got: {violations}"
    )


@pytest.mark.coder
def test_real_shared_body_logic_is_still_flagged(tmp_path):
    """
    SPEC-CODER-DUP-0960: Genuine duplicated logic in the same layer must STILL
    be flagged after header boilerplate is excluded from the comparison.

    The two files have DIFFERENT headers (so the only structural overlap is the
    real, copy-pasted function body) — proving the detector stays sound.
    """
    shared_logic = '''
def process(data):
    step_one = data + 1
    step_two = step_one * 2
    step_three = step_two - 3
    step_four = step_three / 4
    return step_four
'''
    file_a = _write_domain_file(tmp_path, "alpha", '''"""Alpha."""
from __future__ import annotations

from typing import Optional
''' + shared_logic)
    file_b = _write_domain_file(tmp_path, "beta", '''"""Beta module with a longer distinct docstring header."""
import os
import sys
''' + shared_logic)

    violations = find_intra_layer_duplicates({"domain": [file_a, file_b]}, 5)

    assert violations, (
        "Genuine duplicated body logic across same-layer files must still be "
        "flagged after header boilerplate is excluded"
    )
