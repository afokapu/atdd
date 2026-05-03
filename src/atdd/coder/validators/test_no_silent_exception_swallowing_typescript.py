"""
Detect silent exception swallowing in TypeScript / JSX production code.

A silent swallow is a ``try { ... } catch (e) { ... }`` block whose handler:

* makes no observable reaction (no logger call, no ``throw``)
* AND returns a value (or has an empty body)

BE parity: ``test_no_silent_exception_swallowing_python.py``.
Convention: ``src/atdd/coder/conventions/logging.convention.yaml``
            (rule ``COACH-SILENT-SWALLOW-001``)

Detection here is regex-based for tractability — TypeScript AST tooling
introduces a Node toolchain dependency. The regex pass identifies catch
blocks, balances braces to extract the handler body, then runs the same
"no-log + no-throw + has-return-or-empty" predicate as the Python AST pass.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Tuple

import pytest
import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators._violation import Violation
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()
WEB_SRC = REPO_ROOT / "web" / "src"
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
LOGGING_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "logging.convention.yaml"

FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "silent_swallow"
)


# ---------------------------------------------------------------------------
# Rule constants (mirrored in logging.convention.yaml)
# ---------------------------------------------------------------------------
RULE_ID = "COACH-SILENT-SWALLOW-001"
RULE_SEVERITY = 4
SUPPRESSION_MARKER = f"atdd:suppress({RULE_ID})"


_SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", ".nuxt",
    "coverage", "__pycache__", ".cache", "__tests__", "__mocks__",
    ".venv", "venv", "fixtures",
}
_TS_EXTENSIONS = {".ts", ".tsx"}

_TEST_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------
def _is_test_path(file_path: Path) -> bool:
    name = file_path.name
    if name.endswith(_TEST_SUFFIXES):
        return True
    for parent in file_path.parents:
        if parent.name in {"__tests__", "tests", "test", "fixtures"}:
            return True
    return False


def _collect_files(*scan_dirs: Path) -> List[Path]:
    out: List[Path] = []
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(scan_dir):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                if not any(fname.endswith(ext) for ext in _TS_EXTENSIONS):
                    continue
                fp = Path(dirpath) / fname
                if _is_test_path(fp):
                    continue
                out.append(fp)
    return out


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
# Match `catch` clause start: `catch (e)`, `catch (err: unknown)`, or `catch {`.
# Capture trails immediately before the opening brace — we then balance braces
# manually to find the matching close.
_CATCH_RE = re.compile(
    r"""\bcatch\b\s*(?:\(\s*[^)]*\)\s*)?\{""",
    re.MULTILINE,
)

# Logger call inside a handler body. We accept any of:
#   logger.X(...), log.X(...), console.X(...) [error/warn only],
#   this.logger.X(...), <ident>.logger.X(...).
_LOGGER_CALL_RE = re.compile(
    r"""(?:^|[^\w$])"""
    r"""(?:[\w$.]*?(?:logger|log)|console)\."""
    r"""(?:debug|info|warn|warning|error|critical|exception|log|fatal|trace)\s*\(""",
    re.IGNORECASE,
)

# `throw` keyword (re-throw, throw new Error, throw e, etc.) — case-sensitive,
# must be a standalone keyword.
_THROW_RE = re.compile(r"""(?:^|[^\w$])throw\b""", re.MULTILINE)

# `return` keyword inside the handler.
_RETURN_RE = re.compile(r"""(?:^|[^\w$])return\b""", re.MULTILINE)


def _strip_strings_and_comments(src: str) -> str:
    """Crudely remove string literals and comments so regex anchors don't fire
    inside them. Replaces matches with same-length whitespace to preserve byte
    offsets used for line-number recovery."""
    out: List[str] = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        # Line comment
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            if j == -1:
                j = n
            out.append(" " * (j - i))
            i = j
            continue
        # Block comment
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            if j == -1:
                j = n
            else:
                j += 2
            out.append(_blanked(src[i:j]))
            i = j
            continue
        # String / template literal
        if c in ("'", '"', "`"):
            quote = c
            j = i + 1
            while j < n:
                if src[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if src[j] == quote:
                    j += 1
                    break
                j += 1
            out.append(_blanked(src[i:j]))
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _blanked(s: str) -> str:
    """Replace all non-newline characters with spaces."""
    return "".join(ch if ch == "\n" else " " for ch in s)


def _balance_braces(src: str, open_idx: int) -> int:
    """Given the offset of an opening ``{``, return the matching close ``}``
    offset (inclusive). Falls back to len(src) if unbalanced (defensive)."""
    depth = 0
    i = open_idx
    n = len(src)
    while i < n:
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n - 1


def _line_of_offset(src: str, offset: int) -> int:
    """1-based line number for a byte offset."""
    return src.count("\n", 0, offset) + 1


def _check_suppression(src_lines: List[str], lineno: int) -> bool:
    """Inline pragma on the catch line silences this rule."""
    idx = lineno - 1
    if 0 <= idx < len(src_lines):
        if SUPPRESSION_MARKER in src_lines[idx]:
            return True
    return False


def detect_silent_swallows_ts(file_path: Path) -> List[Violation]:
    """Return ``Violation`` records for silent-swallow catches in a TS file."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    cleaned = _strip_strings_and_comments(source)
    src_lines = source.splitlines()

    try:
        rel = file_path.relative_to(REPO_ROOT)
    except ValueError:
        rel = file_path

    violations: List[Violation] = []

    for m in _CATCH_RE.finditer(cleaned):
        # Match ends at the offset *after* `{`. Step back one to land on `{`.
        open_brace = m.end() - 1
        close_brace = _balance_braces(cleaned, open_brace)
        body = cleaned[open_brace + 1: close_brace]

        catch_lineno = _line_of_offset(cleaned, m.start())
        if _check_suppression(src_lines, catch_lineno):
            continue

        # Empty body? `catch (e) {}` — silent.
        if body.strip() == "":
            violations.append(Violation(
                rule_id=RULE_ID,
                severity=RULE_SEVERITY,
                location=f"{rel}:{catch_lineno}",
                detail="silent swallow (empty catch body) — no log, no throw",
            ))
            continue

        has_log = bool(_LOGGER_CALL_RE.search(body))
        has_throw = bool(_THROW_RE.search(body))
        has_return = bool(_RETURN_RE.search(body))

        if has_log or has_throw:
            continue

        if has_return:
            violations.append(Violation(
                rule_id=RULE_ID,
                severity=RULE_SEVERITY,
                location=f"{rel}:{catch_lineno}",
                detail="silent swallow — catch body returns without log or throw",
            ))

    return violations


# ---------------------------------------------------------------------------
# Scan helper for ratchet baseline registry
# ---------------------------------------------------------------------------
def scan_silent_swallows_typescript(repo_root: Path) -> Tuple[int, List[Violation]]:
    """Aggregate silent-swallow violations across web/src/."""
    web_src = repo_root / "web" / "src"
    files = _collect_files(web_src)
    violations: List[Violation] = []
    for f in files:
        violations.extend(detect_silent_swallows_ts(f))
    return len(violations), violations


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.coder
def test_silent_swallow_ts_fixture_violations_detected():
    """
    SPEC-CODER-SILENT-SWALLOW-0002a: detector finds every seeded TS violation.

    Given: fixtures/silent_swallow/typescript_violations/*.ts (intentional swallows)
    When:  detect_silent_swallows_ts runs on each fixture
    Then:  every fixture produces at least one Violation with the canonical
           rule_id and severity.
    """
    fixtures_dir = FIXTURES_DIR / "typescript_violations"
    if not fixtures_dir.exists():
        pytest.fail(f"Missing fixture dir: {fixtures_dir}")

    fixture_files = list(fixtures_dir.rglob("*.ts")) + list(fixtures_dir.rglob("*.tsx"))
    assert fixture_files, f"No fixture files in {fixtures_dir}"

    for fixture in fixture_files:
        violations = detect_silent_swallows_ts(fixture)
        assert violations, (
            f"Expected silent-swallow violations in {fixture.name} "
            f"but detector found none"
        )
        for v in violations:
            assert v.rule_id == RULE_ID, f"Wrong rule_id: {v.rule_id}"
            assert v.severity == RULE_SEVERITY, f"Wrong severity: {v.severity}"


@pytest.mark.coder
def test_silent_swallow_ts_fixture_clean_no_false_positives():
    """
    SPEC-CODER-SILENT-SWALLOW-0002b: zero false positives on acceptable TS shapes.

    Given: fixtures/silent_swallow/typescript_clean/*.ts
    When:  detect_silent_swallows_ts runs
    Then:  no Violations are produced.
    """
    fixtures_dir = FIXTURES_DIR / "typescript_clean"
    if not fixtures_dir.exists():
        pytest.fail(f"Missing fixture dir: {fixtures_dir}")

    fixture_files = list(fixtures_dir.rglob("*.ts")) + list(fixtures_dir.rglob("*.tsx"))
    assert fixture_files, f"No fixture files in {fixtures_dir}"

    spurious: List[str] = []
    for fixture in fixture_files:
        violations = detect_silent_swallows_ts(fixture)
        for v in violations:
            spurious.append(f"  {fixture.name}: {v}")

    if spurious:
        pytest.fail(
            "False positives on acceptable TS patterns:\n\n"
            + "\n".join(spurious)
        )


@pytest.mark.coder
def test_no_silent_exception_swallowing_typescript():
    """
    SPEC-CODER-SILENT-SWALLOW-0002: no silent catch-swallow regressions in TS.

    Scans REPO_ROOT/web/src/ for silent exception swallowing. Uses ratchet
    baseline so pre-existing violations are tolerated until they are migrated,
    but new violations fail.

    Given: production .ts/.tsx files under web/src/ (excluding tests, fixtures)
    When:  regex scan for try/catch handlers with no log / no throw that return
    Then:  violation count does not exceed baseline (auto-seeds first run)

    Convention: src/atdd/coder/conventions/logging.convention.yaml
                (rule COACH-SILENT-SWALLOW-001)
    BE parity:  test_no_silent_exception_swallowing_python.py
    """
    if not WEB_SRC.exists():
        pytest.skip("No web/src/ directory found")

    count, violations = scan_silent_swallows_typescript(REPO_ROOT)
    assert_disposition_satisfied(
        validator_id="silent_exception_swallowing_typescript",
        violations=violations,
    )


@pytest.mark.coder
def test_silent_swallow_ts_rule_declared_in_convention():
    """
    SPEC-CODER-SILENT-SWALLOW-0002c: convention declares the TS-applicable rule.

    Given: src/atdd/coder/conventions/logging.convention.yaml
    When:  loading the file
    Then:  COACH-SILENT-SWALLOW-001 is declared with severity 4 and applies
           to the TS scan scope (web/src/).
    """
    if not LOGGING_CONVENTION.exists():
        pytest.fail(f"Missing convention: {LOGGING_CONVENTION}")

    with open(LOGGING_CONVENTION, "r", encoding="utf-8") as fh:
        convention = yaml.safe_load(fh)

    rules = {r["id"]: r for r in convention.get("rules", [])}
    if RULE_ID not in rules:
        pytest.fail(
            f"Rule {RULE_ID} not found in {LOGGING_CONVENTION}; "
            f"available rule ids: {sorted(rules.keys())}"
        )

    rule = rules[RULE_ID]
    assert rule["severity"] == RULE_SEVERITY

    scan_scope = convention.get("scan_scope", {})
    rule_scope = scan_scope.get(RULE_ID, {})
    includes = rule_scope.get("include", [])
    assert any("web/src" in inc for inc in includes), (
        f"Expected web/src/ in scan_scope.{RULE_ID}.include, got: {includes}"
    )
