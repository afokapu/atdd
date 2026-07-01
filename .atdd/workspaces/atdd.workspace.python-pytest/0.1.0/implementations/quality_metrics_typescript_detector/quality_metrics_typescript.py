"""python-pytest detector for the coder REFACTOR-phase TypeScript quality metrics.

Realizes the agnostic "TypeScript source meets minimum quality metrics" obligation
for the TYPESCRIPT/TSX stack. ONE detector run carries TWO distinct rule_ids — the
v1.1 multi-rule output channel (PROVIDER-CONTRACT-v1.1.md §3). Both rule_ids are
disposition `strict` (aggregated downstream by the consumer, §1):

  * coder.refactor.quality-mi-typescript       — approximate MI >= 20
  * coder.refactor.quality-comments-typescript — comment ratio >= 10%

The MI here is a REGEX approximation (no radon, no AST, no tree-sitter) — the SEI
formula with a regex-estimated Halstead volume, exactly as core. It is therefore
PURE STDLIB and fires deterministically (unlike the Python MI rule, which is
radon-coupled — those are SEPARATE detectors per the documented -python /
-typescript provider split).

PROVENANCE — ported from core
    src/atdd/coder/validators/test_quality_metrics_typescript.py
        :: find_typescript_files / calculate_maintainability_index_ts /
           _halstead_volume / _strip_comments / _comment_ratio_from_source /
           calculate_comment_ratio_ts / scan_maintainability_index_ts /
           scan_comment_ratio_ts
    (origin/main read-only). The regex metrics are copied behavior-for-behavior;
    the ``atdd.coach.*`` substrate couplings were REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_MI_TS`` / ``RULE_COMMENTS_TS``
    constants. Authoritative metadata (severity 2; both strict) lives in the
    convention nodes.
  * ``Violation``  -> plain dicts in the v1.1 shape
    ``{rule_id, file, line, col, evidence, source_line}`` (§3.2).
  * ``find_repo_root`` + ``REPO_ROOT / "web" / "src"`` global dir  -> REMOVED.
    Scan scope is supplied via ``ATDD_SCAN_ROOTS`` / ``ATDD_SCAN_EXCLUDES`` (§2);
    each scan root is treated as a web/src stack root and walked directly.
  * ``assert_disposition_satisfied`` (ratchet baseline)  -> NOT PORTED. Both
    rule_ids are strict; aggregation is the downstream consumer's job (§1).

Pure stdlib (``math``, ``re``, ``fnmatch``, ``pathlib``) — no third-party or core
imports.
"""
from __future__ import annotations

import fnmatch
import math
import re
from pathlib import Path

# Rule ids this detector emits — both disposition `strict`.
RULE_MI_TS = "coder.refactor.quality-mi-typescript"
RULE_COMMENTS_TS = "coder.refactor.quality-comments-typescript"

# Thresholds — copied verbatim from core (parity with the Python validator).
MIN_MAINTAINABILITY_INDEX = 20
MIN_COMMENT_RATIO = 0.10  # 10%

_SKIP_DIRS = {
    "node_modules", "dist", "build", ".next", ".nuxt",
    "coverage", ".cache", "__tests__", "__mocks__",
}
_TS_EXTENSIONS = {".ts", ".tsx"}

# Regex metric tables — copied verbatim from core test_quality_metrics_typescript.
_OPERATORS = re.compile(
    r"(?:"
    r"===|!==|==|!=|>=|<=|=>|&&|\|\||>>>=|>>>|>>=|<<=|"
    r"\?\?|\?\.|[+\-*/%&|^~!<>=]=?|"
    r"\.\.\.|"
    r"[{}()\[\];,.:?]"
    r")"
)
_OPERANDS = re.compile(
    r"""(?:"""
    r""""(?:[^"\\]|\\.)*"|"""
    r"""'(?:[^'\\]|\\.)*'|"""
    r"""`(?:[^`\\]|\\.)*`|"""
    r"""\b\d[\d_.eExXbBoO]*\b|"""
    r"""\b[a-zA-Z_$][a-zA-Z0-9_$]*\b"""
    r""")"""
)
_CC_KEYWORDS = re.compile(
    r"\b(?:if|else\s+if|for|while|do|catch|case|&&|\|\|)\b"
)


# ── file discovery (ported from find_typescript_files) ────────────────────────


def is_excluded(ts_file: Path) -> bool:
    """True when ``ts_file`` is out of scope — core's find_typescript_files filter."""
    parts = ts_file.parts
    if any(d in _SKIP_DIRS for d in parts):
        return True
    if ".test." in ts_file.name or ".spec." in ts_file.name:
        return True
    if ts_file.name.startswith("test_") or "/tests/" in str(ts_file):
        return True
    return False


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def find_typescript_files(root: Path, exclude_globs: list[str] | None = None) -> list[Path]:
    """In-scope ``*.ts`` / ``*.tsx`` files under ``root`` (core semantics)."""
    exclude_globs = exclude_globs or []
    if not root.exists():
        return []
    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        if p.suffix not in _TS_EXTENSIONS:
            continue
        if not p.is_file():
            continue
        if is_excluded(p):
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


def _first_line(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                return line
    except OSError:
        pass
    return ""


# ── metrics (ported verbatim) ─────────────────────────────────────────────────


def _strip_comments(source: str) -> str:
    result = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    result = re.sub(r"//[^\n]*", "", result)
    return result


def _halstead_volume(source: str) -> float:
    operators = _OPERATORS.findall(source)
    operands = _OPERANDS.findall(source)
    n1 = len(set(operators))
    n2 = len(set(operands))
    N1 = len(operators)
    N2 = len(operands)
    n = n1 + n2
    N = N1 + N2
    if n <= 1:
        return 1.0
    return N * math.log2(n)


def _comment_ratio_from_source(source: str) -> float:
    lines = source.split("\n")
    total_non_blank = 0
    comment_lines = 0
    in_block_comment = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        total_non_blank += 1
        if in_block_comment:
            comment_lines += 1
            if "*/" in stripped:
                in_block_comment = False
            continue
        if stripped.startswith("/*"):
            comment_lines += 1
            if "*/" not in stripped:
                in_block_comment = True
            continue
        if stripped.startswith("//"):
            comment_lines += 1
            continue
        if stripped.startswith("*"):
            comment_lines += 1
            continue

    return comment_lines / total_non_blank if total_non_blank > 0 else 0.0


def calculate_maintainability_index_ts(file_path: Path) -> float:
    try:
        source = file_path.read_text(encoding="utf-8")
    except Exception:
        return 100.0

    code = _strip_comments(source)
    loc = sum(1 for line in code.split("\n") if line.strip())
    if loc == 0:
        return 100.0

    V = _halstead_volume(code)
    if V <= 0:
        V = 1.0

    cc_matches = _CC_KEYWORDS.findall(source)
    func_count = max(
        1,
        len(re.findall(r"\bfunction\b", source))
        + len(re.findall(r"=>\s*[{(]", source)),
    )
    avg_cc = max(1, len(cc_matches)) / func_count
    cm = _comment_ratio_from_source(source)

    mi = (
        171
        - 5.2 * math.log(V)
        - 0.23 * avg_cc
        - 16.2 * math.log(loc)
        + 50.0 * math.sin(math.sqrt(2.4 * cm))
    )
    return max(0.0, min(100.0, mi))


def calculate_comment_ratio_ts(file_path: Path) -> float:
    try:
        source = file_path.read_text(encoding="utf-8")
    except Exception:
        return 0.0
    return _comment_ratio_from_source(source)


# ── violation emitters (emit RAW v1.1 dicts) ──────────────────────────────────


def _mi_violations(file_path: Path, rel: str) -> list[dict]:
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []
    if len(content.split("\n")) < 10:  # core skips small files
        return []
    mi = calculate_maintainability_index_ts(file_path)
    if mi >= MIN_MAINTAINABILITY_INDEX:
        return []
    return [{
        "rule_id": RULE_MI_TS,
        "file": rel,
        "line": 1,
        "col": 0,
        "evidence": f"{rel} MI={mi:.1f}",
        "source_line": _first_line(file_path),
    }]


def _comment_violations(file_path: Path, rel: str) -> list[dict]:
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []
    if len(content.split("\n")) < 20:  # core skips small files
        return []
    ratio = calculate_comment_ratio_ts(file_path)
    if ratio >= MIN_COMMENT_RATIO:
        return []
    return [{
        "rule_id": RULE_COMMENTS_TS,
        "file": rel,
        "line": 1,
        "col": 0,
        "evidence": f"{rel} {ratio * 100:.1f}%",
        "source_line": _first_line(file_path),
    }]


# ── public scan API (the v1.1 contract surface) ───────────────────────────────


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan every web/src stack ``root`` and return RAW v1.1 violation dicts.

    Both MI and comments are per-file rules. ``file`` is reported relative to the
    file's own scan root.
    """
    exclude_globs = exclude_globs or []
    violations: list[dict] = []
    for r in roots:
        root = Path(r)
        for f in find_typescript_files(root, exclude_globs):
            rel = _rel(root, f)
            violations.extend(_mi_violations(f, rel))
            violations.extend(_comment_violations(f, rel))
    return violations


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Single-root convenience wrapper over ``scan_roots``."""
    return scan_roots([Path(root)], exclude_globs)
