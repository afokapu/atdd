"""python-pytest detector for coder.refactor.complexity-*-typescript (THREE rule_ids).

Realizes the agnostic REFACTOR-phase complexity obligations for the TypeScript/TSX
stack — the language-specific siblings of the Python complexity rules. ONE
detector run carries THREE distinct rule_ids (the v1.1 multi-rule output channel,
PROVIDER-CONTRACT-v1.1.md §3), exactly the multi binding the core validator
performs:

  * coder.refactor.complexity-cyclomatic-typescript — cyclomatic complexity > 10
  * coder.refactor.complexity-nesting-typescript    — nesting depth > 4
  * coder.refactor.complexity-length-typescript     — function length (LOC) > 50

All three are disposition `strict`; the strict aggregation is the downstream
consumer's job (§1). The detector emits RAW factual violations only.

Like the Wave-1 dead-code / gsap TS detectors, this is a PYTHON detector that
inspects TS source via regex + brace matching — NO TypeScript runtime, no
tree-sitter. It runs under the python-pytest provider, distinct from a future
node/vitest TS workspace for validators that require real TS semantics.

PROVENANCE — ported from core
    src/atdd/coder/validators/test_complexity_typescript.py
        :: find_typescript_files / extract_functions_ts / _find_opening_brace /
           _match_braces / calculate_cyclomatic_complexity_ts /
           calculate_nesting_depth_ts / count_function_lines_ts /
           scan_cyclomatic_complexity_ts / scan_nesting_depth_ts /
           scan_function_length_ts
    (origin/main, refactor.convention.yaml blob 3c4ee089cff5ec9e). The regex /
    brace-matching logic is copied behavior-for-behavior; the ``atdd.coach.*``
    substrate couplings were REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_*_TS`` constants. Authoritative
    metadata (severities 2/3; all three strict) lives in the convention nodes.
  * ``Violation``  -> plain dicts in the v1.1 shape
    ``{rule_id, file, line, col, evidence, source_line}`` (§3.2). Core never
    tracked a column, so ``col`` is 0 (consistent with the Wave-1 detectors).
  * ``find_repo_root`` + fixed ``REPO_ROOT / "web" / "src"`` root  -> REMOVED.
    Scan scope is supplied explicitly via ``ATDD_SCAN_ROOTS`` /
    ``ATDD_SCAN_EXCLUDES`` (§2); never auto-discovered. Each ``ATDD_SCAN_ROOTS``
    entry IS a web/src-equivalent root and is scanned directly, with core's
    ``_SKIP_DIRS`` and test/spec exclusions preserved verbatim.
  * ``assert_disposition_satisfied`` (ratchet baseline)  -> NOT PORTED. All three
    rule_ids are strict, aggregated downstream by the consumer (§1).

ONE DOCUMENTED NON-VERBATIM DEVIATION (off-by-one bug repair):
  Core's ``extract_functions_ts`` calls ``_find_opening_brace(content,
  match.end())`` — a position AFTER the params' opening "(". The param list's
  closing ")" then drives ``paren_depth`` to -1 before the body "{" is reached,
  so core finds NO brace and truncates every function body to its single
  signature line. Under that bug the metric helpers (cyclomatic / nesting /
  length — all of which split the body on "\n") are dead code and the core TS
  complexity validator is effectively INERT (it only ever emits when the ratchet
  baseline is non-zero, which it never reaches). Shipping that verbatim would be
  a structurally inert detector that can never realize its obligation nodes — a
  fake green. We make the SMALLEST possible repair: pass ``match.end() - 1`` (the
  index OF the "(") so the param paren balances and the body brace is found,
  restoring exactly the multi-line extraction the metric functions were written
  to consume. No metric or threshold logic is altered. See the inline comment at
  the call site. This deviation is surfaced in the migration report.

Pure stdlib (``re``, ``fnmatch``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import List, Tuple

# The convention rule_ids this detector realizes (all disposition: strict).
RULE_CYCLO_TS = "coder.refactor.complexity-cyclomatic-typescript"  # cyclomatic > 10
RULE_NEST_TS = "coder.refactor.complexity-nesting-typescript"      # nesting depth > 4
RULE_LEN_TS = "coder.refactor.complexity-length-typescript"        # function LOC > 50

# Thresholds — copied verbatim from core test_complexity_typescript.py.
MAX_CYCLOMATIC_COMPLEXITY = 10
MAX_NESTING_DEPTH = 4
MAX_FUNCTION_LINES = 50

_SKIP_DIRS = {
    "node_modules", "dist", "build", ".next", ".nuxt",
    "coverage", ".cache", "__tests__", "__mocks__",
}
_TS_EXTENSIONS = {".ts", ".tsx"}


# ── file discovery (ported; rooted at the supplied scan root) ──────────────────


def find_typescript_files(root: Path, exclude_globs: list[str] | None = None) -> List[Path]:
    """Find TS/TSX source files under ``root`` (excluding tests). Core's filters.

    Mirrors core ``find_typescript_files`` exactly, except the root is the supplied
    scan root (not ``REPO_ROOT / "web" / "src"``) and an optional ``exclude_globs``
    (relative-path fnmatch) is honored (§2).
    """
    if not root.exists():
        return []
    exclude_globs = exclude_globs or []
    files: List[Path] = []
    for ts_file in sorted(root.rglob("*")):
        if ts_file.suffix not in _TS_EXTENSIONS:
            continue
        if not ts_file.is_file():
            continue
        parts = ts_file.parts
        if any(d in _SKIP_DIRS for d in parts):
            continue
        if ".test." in ts_file.name or ".spec." in ts_file.name:
            continue
        if ts_file.name.startswith("test_") or "/tests/" in str(ts_file):
            continue
        if exclude_globs:
            try:
                rel = ts_file.relative_to(root)
            except ValueError:
                rel = ts_file
            if any(fnmatch.fnmatch(str(rel), pat) for pat in exclude_globs):
                continue
        files.append(ts_file)
    return files


# ── function extraction (regex + brace matching; ported verbatim) ──────────────

_FUNC_PATTERNS = [
    re.compile(
        r"^(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*"
        r"(?:<[^>]*>)?"
        r"\s*\(",
        re.MULTILINE,
    ),
    re.compile(
        r"^(?:export\s+)?(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*"
        r"(?::\s*[^=]+?)?"
        r"\s*=\s*(?:async\s+)?(?:function\s*)?(?:<[^>]*>)?\s*\(",
        re.MULTILINE,
    ),
]


def extract_functions_ts(file_path: Path) -> List[Tuple[str, int, str]]:
    """Extract (function_name, 1-based line, function_body) tuples. Ported verbatim."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []

    functions: List[Tuple[str, int, str]] = []

    for pattern in _FUNC_PATTERNS:
        for match in pattern.finditer(content):
            func_name = match.group(1)
            line_num = content[: match.start()].count("\n") + 1

            # DEVIATION FROM VERBATIM CORE (documented; see module note below).
            # Core calls ``_find_opening_brace(content, match.end())`` — a
            # position AFTER the params' opening "(". The param list's closing
            # ")" then drives ``paren_depth`` to -1 BEFORE the body "{" is
            # reached, so core never finds the brace and truncates every
            # function body to its signature line. The metric helpers (all split
            # on "\n") then become dead code and the validator is inert. We pass
            # ``match.end() - 1`` (the index OF the "(") so the param paren is
            # balanced and the body brace is found — restoring exactly the
            # multi-line extraction the core metric functions were written to
            # consume. Pure off-by-one repair; NO metric/threshold logic changed.
            body_start = _find_opening_brace(content, match.end() - 1)
            if body_start == -1:
                stmt_end = content.find("\n", match.end())
                if stmt_end == -1:
                    stmt_end = len(content)
                body = content[match.start():stmt_end]
                functions.append((func_name, line_num, body))
                continue

            body_end = _match_braces(content, body_start)
            if body_end == -1:
                continue

            body = content[match.start():body_end + 1]
            functions.append((func_name, line_num, body))

    return functions


def _find_opening_brace(content: str, start: int) -> int:
    """Find the first '{' after start, skipping parens and arrow. Ported verbatim."""
    i = start
    paren_depth = 0
    while i < len(content):
        ch = content[i]
        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth -= 1
        elif ch == "{" and paren_depth == 0:
            return i
        elif ch == "\n" and paren_depth == 0:
            segment = content[start:i]
            if "=>" in segment and "{" not in segment:
                return -1
        i += 1
    return -1


def _match_braces(content: str, open_pos: int) -> int:
    """Find the matching closing brace for the one at open_pos. Ported verbatim."""
    depth = 0
    i = open_pos
    in_string = None
    in_template = 0
    in_line_comment = False
    in_block_comment = False

    while i < len(content):
        ch = content[i]

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and i + 1 < len(content) and content[i + 1] == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_string:
            if ch == "\\" and i + 1 < len(content):
                i += 2
                continue
            if in_string == "`":
                if ch == "$" and i + 1 < len(content) and content[i + 1] == "{":
                    in_template += 1
                    i += 2
                    continue
                if ch == "}" and in_template > 0:
                    in_template -= 1
                    i += 1
                    continue
            if ch == in_string and in_template == 0:
                in_string = None
            i += 1
            continue

        if ch == "/" and i + 1 < len(content):
            if content[i + 1] == "/":
                in_line_comment = True
                i += 2
                continue
            if content[i + 1] == "*":
                in_block_comment = True
                i += 2
                continue

        if ch in ("'", '"', "`"):
            in_string = ch
            i += 1
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i

        i += 1

    return -1


# ── metrics (ported verbatim) ──────────────────────────────────────────────────


def calculate_cyclomatic_complexity_ts(function_body: str) -> int:
    """Cyclomatic complexity for a TS function body. Ported verbatim."""
    complexity = 1
    keywords = ["if", "else\\s+if", "for", "while", "do", "catch", "case"]
    for kw in keywords:
        pattern = r"\b" + kw + r"\b"
        complexity += len(re.findall(pattern, function_body))

    complexity += len(re.findall(r"&&", function_body))
    complexity += len(re.findall(r"\|\|", function_body))
    complexity += len(re.findall(r"\?\?", function_body))
    complexity += len(re.findall(r"[^\s?]\s*\?(?![\s.?:])\s*[^:]", function_body))
    return complexity


def calculate_nesting_depth_ts(function_body: str) -> int:
    """Maximum nesting depth inside a TS function body. Ported verbatim."""
    max_depth = 0
    control_depth = 0
    lines = function_body.split("\n")

    _CONTROL_KW = re.compile(r"\b(if|else|for|while|do|switch|try|catch|finally)\b")

    brace_depth = 0
    base_depth = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
            continue

        opens = stripped.count("{")
        closes = stripped.count("}")

        if base_depth is None and opens > 0:
            base_depth = brace_depth

        prev_depth = brace_depth
        has_control = bool(_CONTROL_KW.search(stripped))
        brace_depth += opens - closes

        if has_control and opens > 0:
            control_depth = brace_depth - (base_depth or 0)
            max_depth = max(max_depth, control_depth)
        elif opens > 0:
            pass

        if closes > 0 and brace_depth < prev_depth:
            control_depth = max(0, brace_depth - (base_depth or 0))

    return max_depth


def count_function_lines_ts(function_body: str) -> int:
    """Count lines of code (excluding blank/comment lines). Ported verbatim."""
    count = 0
    in_block_comment = False
    for line in function_body.split("\n"):
        stripped = line.strip()
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            continue
        if stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block_comment = True
            continue
        if not stripped:
            continue
        if stripped.startswith("//"):
            continue
        count += 1
    return count


# ── violation emitters (emit RAW v1.1 dicts) ──────────────────────────────────


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _body_first_line(function_body: str) -> str:
    return function_body.split("\n")[0]


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> List[dict]:
    """Scan one web/src-equivalent ``root`` and return RAW v1.1 violation dicts.

    Runs all three metric scans per file and emits ``{rule_id,file,line,col,
    evidence,source_line}`` for every threshold breach. ``file`` is relative to
    ``root``; ``col`` is 0 (core tracked only ``rel_path:line``).
    """
    root = Path(root)
    violations: List[dict] = []
    for ts_file in find_typescript_files(root, exclude_globs):
        rel = _rel(root, ts_file)
        functions = extract_functions_ts(ts_file)

        # cyclomatic — core skips functions with < 3 code lines.
        for func_name, line_num, func_body in functions:
            if count_function_lines_ts(func_body) < 3:
                continue
            complexity = calculate_cyclomatic_complexity_ts(func_body)
            if complexity > MAX_CYCLOMATIC_COMPLEXITY:
                violations.append({
                    "rule_id": RULE_CYCLO_TS,
                    "file": rel,
                    "line": line_num,
                    "col": 0,
                    "evidence": f"{func_name} complexity={complexity} (>{MAX_CYCLOMATIC_COMPLEXITY})",
                    "source_line": _body_first_line(func_body),
                })

        # nesting depth
        for func_name, line_num, func_body in functions:
            depth = calculate_nesting_depth_ts(func_body)
            if depth > MAX_NESTING_DEPTH:
                violations.append({
                    "rule_id": RULE_NEST_TS,
                    "file": rel,
                    "line": line_num,
                    "col": 0,
                    "evidence": f"{func_name} depth={depth} (>{MAX_NESTING_DEPTH})",
                    "source_line": _body_first_line(func_body),
                })

        # function length
        for func_name, line_num, func_body in functions:
            lines = count_function_lines_ts(func_body)
            if lines > MAX_FUNCTION_LINES:
                violations.append({
                    "rule_id": RULE_LEN_TS,
                    "file": rel,
                    "line": line_num,
                    "col": 0,
                    "evidence": f"{func_name} lines={lines} (>{MAX_FUNCTION_LINES})",
                    "source_line": _body_first_line(func_body),
                })

    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> List[dict]:
    """Scan every root and return the concatenated RAW violation list."""
    out: List[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
