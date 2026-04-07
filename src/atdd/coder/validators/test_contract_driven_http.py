"""
Test that TypeScript code uses HttpClient instead of raw fetch().

Validates:
- No raw fetch() calls outside whitelisted files
- Whitelist configured via .atdd/config.yaml contract_driven_http.whitelist

Convention: src/atdd/coder/conventions/frontend.convention.yaml
Spec: SPEC-CODER-CONTRACT-0001
"""

import fnmatch
import os
import re
import yaml
import pytest
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from atdd.coach.utils.repo import find_repo_root


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()
WEB_SRC_DIR = REPO_ROOT / "web" / "src"
CONFIG_PATH = REPO_ROOT / ".atdd" / "config.yaml"

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".dart_tool",
    "build", ".pub-cache", "dist", ".next", ".nuxt", "coverage",
    ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
}

_TS_EXTENSIONS = (".ts", ".tsx")

# Matches `fetch(` and `fetch (` but not identifiers like `prefetch(`
_RAW_FETCH_RE = re.compile(r"(?<![.\w])fetch\s*\(")


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
def load_whitelist() -> List[str]:
    """Load whitelist globs from .atdd/config.yaml contract_driven_http.whitelist."""
    if not CONFIG_PATH.exists():
        return []
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data.get("contract_driven_http", {}).get("whitelist", [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------
def _is_test_file(path: Path) -> bool:
    """Return True if *path* is a test file that should be skipped."""
    name = path.name
    if name.endswith(".test.ts") or name.endswith(".test.tsx"):
        return True
    if name.endswith(".spec.ts") or name.endswith(".spec.tsx"):
        return True
    # Inside __tests__/ directory
    if "__tests__" in path.parts:
        return True
    return False


def find_ts_files(base_dir: Path, whitelist: List[str]) -> List[Path]:
    """Walk *base_dir* for TS/TSX files, excluding tests and whitelisted paths."""
    files: List[Path] = []
    if not base_dir.exists():
        return files

    for dirpath, dirnames, filenames in os.walk(base_dir):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if not any(fname.endswith(ext) for ext in _TS_EXTENSIONS):
                continue
            full = Path(dirpath) / fname
            if _is_test_file(full):
                continue
            # Check whitelist globs against relative path from base_dir
            try:
                rel = str(full.relative_to(base_dir))
            except ValueError:
                rel = str(full)
            if any(fnmatch.fnmatch(rel, pat) for pat in whitelist):
                continue
            files.append(full)
    return files


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------
def scan_raw_fetch(files: List[Path]) -> List[Dict]:
    """Scan files for raw fetch() calls. Returns list of violation dicts."""
    violations: List[Dict] = []
    for file_path in files:
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Skip single-line comments
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue
            if _RAW_FETCH_RE.search(line):
                snippet = stripped[:80] + ("..." if len(stripped) > 80 else "")
                violations.append({
                    "file": file_path,
                    "line": lineno,
                    "detail": snippet,
                })
    return violations


# ---------------------------------------------------------------------------
# Baseline helper (for baseline.py registry)
# ---------------------------------------------------------------------------
def analyze_contract_driven_http(repo_root: Path) -> Tuple[int, Sequence]:
    """Run scanner and return (count, violation_strings) for baseline registry."""
    web_src = repo_root / "web" / "src"
    if not web_src.exists():
        return 0, []
    whitelist = load_whitelist()
    files = find_ts_files(web_src, whitelist)
    violations = scan_raw_fetch(files)
    formatted = [
        f"{v['file'].relative_to(repo_root)}:{v['line']}  {v['detail']}"
        for v in violations
    ]
    return len(formatted), formatted


# ---------------------------------------------------------------------------
# Violation formatter
# ---------------------------------------------------------------------------
def _format_violations(violations: List[Dict], base_dir: Path) -> str:
    """Format violations for pytest.fail() output."""
    lines = []
    for v in violations[:10]:
        try:
            rel = v["file"].relative_to(base_dir)
        except ValueError:
            rel = v["file"]
        lines.append(
            f"{rel}:{v['line']}\n"
            f"  {v['detail']}\n"
            f"  Suggestion: Use HttpClient instead of raw fetch()"
        )
    header = (
        f"\n\nFound {len(violations)} raw fetch() call(s) — "
        f"use HttpClient for contract-driven HTTP access:\n\n"
    )
    body = "\n\n".join(lines)
    tail = ""
    if len(violations) > 10:
        tail = f"\n\n... and {len(violations) - 10} more"
    return header + body + tail


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.coder
def test_no_raw_fetch_calls(ratchet_baseline):
    """
    SPEC-CODER-CONTRACT-0001: No raw fetch() calls in frontend TypeScript code.

    All HTTP access must go through HttpClient so that contracts, interceptors,
    and telemetry are applied uniformly.  Raw fetch() bypasses these safeguards.

    Given: TypeScript/TSX files in web/src/
    When:  Scanning for raw fetch() calls
    Then:  No raw fetch() usage found outside whitelisted files
    """
    if not WEB_SRC_DIR.exists():
        pytest.skip("No web/src directory found — skipping contract-driven HTTP check")

    whitelist = load_whitelist()
    files = find_ts_files(WEB_SRC_DIR, whitelist)
    if not files:
        pytest.skip("No TypeScript files found in web/src/")

    violations = scan_raw_fetch(files)

    ratchet_baseline.assert_no_regression(
        validator_id="contract_driven_http",
        current_count=len(violations),
        violations=[
            f"{v['file'].relative_to(REPO_ROOT)}:{v['line']}  {v['detail']}"
            for v in violations
        ],
    )

    if violations:
        pytest.fail(_format_violations(violations, REPO_ROOT))
