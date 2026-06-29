"""python-pytest detector for the coder REFACTOR-phase quality metrics.

Realizes the agnostic "Python source meets minimum quality metrics" obligation
for the PYTHON stack. ONE detector run carries FIVE distinct rule_ids — the v1.1
multi-rule output channel (PROVIDER-CONTRACT-v1.1.md §3). Every rule_id is
disposition `strict` (aggregated downstream by the consumer, §1):

  * coder.refactor.quality-mi          — maintainability index (radon) >= 20
  * coder.refactor.quality-comments    — comment/docstring ratio >= 10%
  * coder.refactor.quality-duplication — no >=5-statement AST fragment shared
                                         across two different files
  * coder.refactor.quality-naming      — PascalCase classes / UPPER_CASE consts
  * coder.refactor.quality-file-length — files over the 500-line report threshold

PROVENANCE — ported from core
    src/atdd/coder/validators/test_quality_metrics.py
        :: find_python_files / calculate_maintainability_index /
           calculate_comment_ratio / find_duplicate_code_blocks /
           check_naming_consistency / scan_file_line_count
    plus the AST fragment matcher it imports from
    src/atdd/coder/validators/test_duplication_detector.py
        :: extract_fragments / _ASTNormalizer / _hash_statements /
           strip_module_header
    (origin/main read-only). Detection is copied behavior-for-behavior; the
    ``atdd.coach.*`` substrate couplings were REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_*`` constants. Authoritative
    metadata (severity 2; all strict) lives in the convention nodes, not bound at
    import.
  * ``Violation``  -> plain dicts in the v1.1 shape
    ``{rule_id, file, line, col, evidence, source_line}`` (§3.2). The core
    ``location`` + ``detail`` are preserved inside ``file`` (scan-root-relative
    path) + ``line``/``col`` + ``evidence``.
  * ``find_repo_root`` + ``REPO_ROOT / "python"`` single global dir  -> REMOVED.
    Scan scope is supplied explicitly via ``ATDD_SCAN_ROOTS`` / ``ATDD_SCAN_EXCLUDES``
    (§2); each scan root is treated as a python stack root and walked directly.
  * ``assert_disposition_satisfied`` (ratchet baseline)  -> NOT PORTED. All five
    rule_ids are strict; aggregation is the downstream consumer's job (§1). The
    quality-file-length rule's report-threshold emission is RAW factual (the file
    exceeds 500 lines); the ratchet-baseline "growth only" disposition is a
    consumer concern, not the provider's.
  * ``from ...test_duplication_detector import extract_fragments``  -> VENDORED
    below (the same AST-normalized matcher, copied from the sibling
    duplication_detector impl) so the detector needs no cross-impl import.

SUBSTRATE NOTE (honest): ``quality-mi`` depends on the third-party ``radon``
package — exactly as core, which wraps ``from radon.metrics import mi_visit`` in a
try/except that returns 100.0 (don't-penalize) when radon is unavailable. This
detector preserves that behavior verbatim: with radon absent, no MI violations are
emitted. ``radon_available()`` exposes the state so proofs can be honest about
which leg they exercised. The other four rules are pure stdlib.

Pure stdlib (``ast``, ``hashlib``, ``re``, ``fnmatch``, ``pathlib``) — plus the
OPTIONAL third-party ``radon`` for MI only. No core imports.
"""
from __future__ import annotations

import ast
import fnmatch
import hashlib
import re
from pathlib import Path

# Rule ids this detector emits — all disposition `strict`.
RULE_MI = "coder.refactor.quality-mi"
RULE_COMMENTS = "coder.refactor.quality-comments"
RULE_DUP = "coder.refactor.quality-duplication"
RULE_NAMING = "coder.refactor.quality-naming"
RULE_FILE_LEN = "coder.refactor.quality-file-length"

# Thresholds — copied verbatim from core test_quality_metrics.py.
MIN_MAINTAINABILITY_INDEX = 20
MIN_COMMENT_RATIO = 0.10           # 10% comments
MIN_DUPLICATE_STATEMENTS = 5       # AST statements per duplicate window
FILE_LINE_REPORT_THRESHOLD = 500   # files OVER this are reported (raw fact)

# Directory names skipped during the walk (caches / vendored / build).
_SKIP_DIRS = frozenset(
    {".git", "node_modules", "dist", "build", ".next", ".nuxt", "coverage",
     "__pycache__", ".cache", ".venv", "venv", "env", ".tox", ".mypy_cache",
     ".pytest_cache"}
)


# ── radon availability (substrate-coupled MI leg) ─────────────────────────────


def radon_available() -> bool:
    """True iff the third-party ``radon`` MI backend can be imported."""
    try:
        from radon.metrics import mi_visit  # noqa: F401
        return True
    except Exception:
        return False


# ── file discovery (ported from find_python_files / scan_file_line_count) ─────


def is_excluded(py_file: Path) -> bool:
    """True when ``py_file`` is out of scope — core's find_python_files filter.

    Core skips ``/test/`` path segments, ``test_*`` basenames, and ``__pycache__``.
    """
    path_str = str(py_file)
    if "/test/" in path_str:
        return True
    if py_file.name.startswith("test_"):
        return True
    if "__pycache__" in path_str:
        return True
    return False


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def find_python_files(root: Path, exclude_globs: list[str] | None = None) -> list[Path]:
    """In-scope ``*.py`` files under ``root`` (core find_python_files semantics)."""
    exclude_globs = exclude_globs or []
    if not root.exists():
        return []
    out: list[Path] = []
    for p in sorted(root.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if is_excluded(p):
            continue
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(root)
        except ValueError:
            rel = p
        if exclude_globs and _matches_exclude(rel, exclude_globs):
            continue
        out.append(p)
    return out


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _line_text(path: Path, lineno: int) -> str:
    """RAW text of 1-based ``lineno`` in ``path`` (no trailing newline), or ''."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""


# ── 1. maintainability index (ported; radon-backed, try/except -> 100.0) ──────


def calculate_maintainability_index(file_path: Path) -> float:
    """Radon MI (``mi_visit(source, multi=True)``); 100.0 when uncomputable.

    Behavior-for-behavior with core: any exception — including ``radon`` being
    absent — yields 100.0 (don't penalize). With radon absent the rule therefore
    never fires; that is the faithful, documented substrate behavior.
    """
    try:
        from radon.metrics import mi_visit
        source = file_path.read_text(encoding="utf-8")
        return mi_visit(source, multi=True)
    except Exception:
        return 100.0


def _mi_violations(file_path: Path, rel: str) -> list[dict]:
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    except Exception:
        return []
    if len(lines) < 10:  # core skips very small files
        return []
    index = calculate_maintainability_index(file_path)
    if index >= MIN_MAINTAINABILITY_INDEX:
        return []
    return [{
        "rule_id": RULE_MI,
        "file": rel,
        "line": 1,
        "col": 0,
        "evidence": f"Maintainability Index: {index:.1f} (min: {MIN_MAINTAINABILITY_INDEX})",
        "source_line": _line_text(file_path, 1),
    }]


# ── 2. comment ratio (ported verbatim) ────────────────────────────────────────


def calculate_comment_ratio(file_path: Path) -> float:
    """Ratio of comment + docstring lines to total non-blank lines (core port)."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return 0.0

    code_lines = 0
    comment_lines = 0
    in_docstring = False
    docstring_delim = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if '"""' in stripped or "'''" in stripped:
            delim = '"""' if '"""' in stripped else "'''"
            if not in_docstring:
                in_docstring = True
                docstring_delim = delim
                comment_lines += 1
                if stripped.count(delim) >= 2:
                    in_docstring = False
                    docstring_delim = None
            else:
                if delim == docstring_delim:
                    in_docstring = False
                    docstring_delim = None
                comment_lines += 1
        elif in_docstring:
            comment_lines += 1
        elif stripped.startswith("#"):
            comment_lines += 1
        else:
            code_lines += 1

    total = code_lines + comment_lines
    return comment_lines / total if total > 0 else 0.0


def _comment_violations(file_path: Path, rel: str) -> list[dict]:
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    except Exception:
        return []
    if len(lines) < 20:  # core skips small files
        return []
    ratio = calculate_comment_ratio(file_path)
    if ratio >= MIN_COMMENT_RATIO:
        return []
    return [{
        "rule_id": RULE_COMMENTS,
        "file": rel,
        "line": 1,
        "col": 0,
        "evidence": f"Comment ratio: {ratio * 100:.1f}% (min: {MIN_COMMENT_RATIO * 100:.0f}%)",
        "source_line": _line_text(file_path, 1),
    }]


# ── 3. duplication (ported; vendored AST fragment matcher) ────────────────────


class _ASTNormalizer(ast.NodeTransformer):
    """Strip variable names and literal values from AST to capture structure only."""

    def visit_Name(self, node: ast.Name) -> ast.Name:
        self.generic_visit(node)
        return ast.copy_location(ast.Name(id="VAR", ctx=node.ctx), node)

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(value=""), node)
        if isinstance(node.value, (int, float, complex)):
            return ast.copy_location(ast.Constant(value=0), node)
        return node


def _hash_statements(stmts: list[ast.stmt]) -> str:
    normalizer = _ASTNormalizer()
    normalized = []
    for stmt in stmts:
        normalized.append(normalizer.visit(ast.parse(ast.unparse(stmt)).body[0]))
    dumped = "\n".join(ast.dump(s) for s in normalized)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:16]


def _is_module_docstring(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _is_import(stmt: ast.stmt) -> bool:
    return isinstance(stmt, (ast.Import, ast.ImportFrom))


def _is_module_constant(stmt: ast.stmt) -> bool:
    return isinstance(stmt, (ast.Assign, ast.AnnAssign))


def strip_module_header(body: list[ast.stmt]) -> list[ast.stmt]:
    """Drop the contiguous leading header-boilerplate prefix (#960, core port)."""
    idx = 0
    n = len(body)
    if idx < n and _is_module_docstring(body[idx]):
        idx += 1
    while idx < n and (_is_import(body[idx]) or _is_module_constant(body[idx])):
        idx += 1
    return body[idx:]


def extract_fragments(file_path: Path, min_statements: int) -> list[tuple[str, int, int]]:
    """Hashable code fragments — (hash, start_line, end_line). Core-faithful."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    fragments: list[tuple[str, int, int]] = []

    def _scan_body(body: list[ast.stmt]) -> None:
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

    _scan_body(strip_module_header(tree.body))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _scan_body(node.body)

    return fragments


def find_duplicate_code_blocks(
    files: list[Path],
) -> list[tuple[Path, Path, int, int]]:
    """Cross-file structural duplicates (core find_duplicate_code_blocks port).

    NOT layer-restricted (that is the sister no-intra-layer rule): any two
    DIFFERENT files sharing a ``MIN_DUPLICATE_STATEMENTS``-statement normalized
    fragment collide. Returns ``(file_a, file_b, start_line_a, end_line_a)``.
    """
    hash_map: dict[str, list[tuple[Path, int, int]]] = {}
    for f in files:
        for h, start, end in extract_fragments(f, MIN_DUPLICATE_STATEMENTS):
            hash_map.setdefault(h, []).append((f, start, end))

    seen_pairs: set = set()
    duplicates: list[tuple[Path, Path, int, int]] = []
    for h, locations in hash_map.items():
        unique_files = {loc[0] for loc in locations}
        if len(unique_files) < 2:
            continue
        first = locations[0]
        for other in locations[1:]:
            if other[0] == first[0]:
                continue
            key = (first[0], other[0], h)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            duplicates.append((first[0], other[0], first[1], first[2]))

    return duplicates


def _duplication_violations(pairs: list[tuple[Path, str]]) -> list[dict]:
    rel_of = {abs_p: rel for abs_p, rel in pairs}
    files = [abs_p for abs_p, _ in pairs]
    out: list[dict] = []
    for file_a, file_b, start_line, end_line in find_duplicate_code_blocks(files):
        rel_a = rel_of.get(file_a, str(file_a))
        rel_b = rel_of.get(file_b, str(file_b))
        span = end_line - start_line + 1
        out.append({
            "rule_id": RULE_DUP,
            "file": rel_a,
            "line": start_line,
            "col": 0,
            "evidence": (
                f"{rel_a}:{start_line}-{end_line} <-> {rel_b} "
                f"({MIN_DUPLICATE_STATEMENTS} identical statements, {span} lines)"
            ),
            "source_line": _line_text(file_a, start_line),
        })
    return out


# ── 4. naming consistency (ported verbatim) ───────────────────────────────────

_PYTEST_SPECIAL_VARS = ["pytest_plugins"]


def check_naming_consistency(file_path: Path) -> list[str]:
    """Naming violations — lowercase classes / lowercase-underscore consts (port)."""
    violations: list[str] = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return violations

    class_pattern = r"class\s+([a-z][a-zA-Z0-9_]*)\s*[:\(]"
    lowercase_classes = re.findall(class_pattern, content)
    for cls in lowercase_classes:
        violations.append(f"Class '{cls}' should use PascalCase")

    const_pattern = r'^([a-z][a-z0-9_]*)\s*=\s*["\'\d\[]'
    for line in content.split("\n"):
        if not line.startswith(" ") and not line.startswith("\t"):  # module level
            match = re.match(const_pattern, line)
            if match and match.group(1).isupper():
                pass
            elif match and match.group(1) in _PYTEST_SPECIAL_VARS:
                pass
            elif match and "_" in match.group(1):
                violations.append(f"Constant '{match.group(1)}' should use UPPER_CASE")

    return violations


def _naming_violations(file_path: Path, rel: str) -> list[dict]:
    out: list[dict] = []
    for detail in check_naming_consistency(file_path):
        out.append({
            "rule_id": RULE_NAMING,
            "file": rel,
            "line": 1,
            "col": 0,
            "evidence": detail,
            "source_line": _line_text(file_path, 1),
        })
    return out


# ── 5. file line count (ported; raw report-threshold fact) ────────────────────


def _file_length_violations(file_path: Path, rel: str) -> list[dict]:
    try:
        line_count = len(file_path.read_text(encoding="utf-8").splitlines())
    except Exception:
        return []
    if line_count <= FILE_LINE_REPORT_THRESHOLD:
        return []
    return [{
        "rule_id": RULE_FILE_LEN,
        "file": rel,
        "line": 1,
        "col": 0,
        "evidence": f"{rel} lines={line_count}",
        "source_line": _line_text(file_path, 1),
    }]


# ── public scan API (the v1.1 contract surface) ───────────────────────────────


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan every python stack ``root`` and return RAW v1.1 violation dicts.

    Per-file rules (MI / comments / naming / file-length) run on each in-scope
    file; the duplication rule pools files across ALL roots (core-faithful — core
    compared every discovered file) so a fragment duplicated across roots is
    caught. ``file`` is reported relative to the file's own scan root.
    """
    exclude_globs = exclude_globs or []
    pairs: list[tuple[Path, str]] = []
    for r in roots:
        root = Path(r)
        for f in find_python_files(root, exclude_globs):
            pairs.append((f, _rel(root, f)))

    violations: list[dict] = []
    for abs_p, rel in pairs:
        violations.extend(_mi_violations(abs_p, rel))
        violations.extend(_comment_violations(abs_p, rel))
        violations.extend(_naming_violations(abs_p, rel))
        violations.extend(_file_length_violations(abs_p, rel))
    violations.extend(_duplication_violations(pairs))
    return violations


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Single-root convenience wrapper over ``scan_roots``."""
    return scan_roots([Path(root)], exclude_globs)
