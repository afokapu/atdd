"""
Test frontend code for known-bad security patterns.

Validates:
- No innerHTML or dangerouslySetInnerHTML usage in TypeScript/JSX files

Conventions from:
- atdd/coder/conventions/security.convention.yaml

Rationale: Direct DOM manipulation via innerHTML is the most common
XSS vector in frontend code.  Safe alternatives exist (textContent,
React's JSX escaping, DOMPurify).

Structured violations (issue #340): emits ``Violation(rule_id="SECURITY-XSS-001", ...)``
records via ``RatchetBaseline.assert_no_regression(violations=...)`` so that
risk-scoring, suppression-audit, and self-fix tooling can route off the rule_id.
The ID grammar is governed by ``src/atdd/coach/specs/rule-id.spec.md``.
"""

import fnmatch
import os
import re
import yaml
import pytest
from pathlib import Path
from typing import Dict, List, Optional

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators._violation import Violation


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()
WEB_DIR = REPO_ROOT / "web"
FRONTEND_DIRS = [
    REPO_ROOT / "web",
    REPO_ROOT / "frontend",
]

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
SECURITY_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "security.convention.yaml"

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".dart_tool",
    "build", ".pub-cache", "dist", ".next", ".nuxt", "coverage",
    ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
}


# ---------------------------------------------------------------------------
# Convention loader
# ---------------------------------------------------------------------------
def load_security_convention() -> Dict:
    """Load security convention YAML.  Returns empty dict when missing."""
    if not SECURITY_CONVENTION.exists():
        return {}
    with open(SECURITY_CONVENTION, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
        return data.get("security", {})


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
def matches_exclusion(
    file_path: Path,
    exclusions: List[str],
    base_dir: Path,
) -> bool:
    """Return True if *file_path* matches any exclusion glob relative to *base_dir*."""
    try:
        rel = str(file_path.relative_to(base_dir))
    except ValueError:
        rel = str(file_path)
    return any(fnmatch.fnmatch(rel, pat) for pat in exclusions)


def find_frontend_files(
    dirs: List[Path],
    extensions: List[str],
    exclude_patterns: Optional[List[str]] = None,
) -> List[Path]:
    """Walk directories for files matching *extensions*, honouring exclusions."""
    exclude_patterns = exclude_patterns or []
    files: List[Path] = []
    for base_dir in dirs:
        if not base_dir.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base_dir):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                if not any(fname.endswith(ext) for ext in extensions):
                    continue
                full = Path(dirpath) / fname
                if matches_exclusion(full, exclude_patterns, base_dir):
                    continue
                files.append(full)
    return files


# ---------------------------------------------------------------------------
# XSS pattern detector  (regex)
# ---------------------------------------------------------------------------
# SPEC-COACH-RULEID-0001: rule_id matching the grammar <DOMAIN>-<TOPIC>-<NNN>.
# Severity 5 = security/blocking per SPEC-COACH-RULEID-0003.
XSS_RULE_ID = "SECURITY-XSS-001"
XSS_RULE_SEVERITY = 5


def check_xss_patterns(
    file_path: Path,
    patterns: List[str],
    base_dir: Path,
) -> List[Violation]:
    """Line-by-line regex scan for XSS-prone DOM patterns.

    Returns structured ``Violation`` records (issue #340).
    """
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    try:
        rel_path = file_path.relative_to(base_dir)
    except ValueError:
        rel_path = file_path

    compiled = [(p, re.compile(p)) for p in patterns]
    violations: List[Violation] = []
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        # Skip comments
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        for pattern_str, regex in compiled:
            if regex.search(line):
                snippet = stripped[:80] + ("..." if len(stripped) > 80 else "")
                violations.append(Violation(
                    rule_id=XSS_RULE_ID,
                    severity=XSS_RULE_SEVERITY,
                    location=f"{rel_path}:{lineno}",
                    detail=f"XSS pattern '{pattern_str}' found: {snippet}",
                ))
    return violations


# ---------------------------------------------------------------------------
# Violation formatter
# ---------------------------------------------------------------------------
def _format_violations(violations: List[Violation]) -> str:
    """Format Violation records for pytest.fail() output."""
    lines = [str(v) for v in violations[:10]]
    header = f"\n\nFound {len(violations)} security violation(s):\n\n"
    body = "\n".join(lines)
    tail = ""
    if len(violations) > 10:
        tail = f"\n\n... and {len(violations) - 10} more"
    return header + body + tail


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.coder
def test_no_xss_prone_patterns(ratchet_baseline):
    """
    SECURITY-XSS-001: No innerHTML or dangerouslySetInnerHTML in frontend code.

    Direct DOM manipulation via innerHTML is the most common XSS vector.
    Use textContent, framework-safe APIs, or DOMPurify instead.

    Given: TypeScript/JSX files in web/ or frontend/
    When:  Scanning for innerHTML and dangerouslySetInnerHTML patterns
    Then:  No XSS-prone DOM manipulation found

    Issue #340: emits structured Violation records through the ratchet so
    that risk-scoring and self-fix tooling can route off rule_id.
    """
    convention = load_security_convention()
    rule = convention.get("rules", {}).get("xss_patterns", {})
    patterns = rule.get("patterns", ["innerHTML", "dangerouslySetInnerHTML", r"outerHTML\s*="])
    extensions = rule.get("file_extensions", [".ts", ".tsx", ".jsx"])
    exclusions = rule.get("exclusions", [])

    files = find_frontend_files(FRONTEND_DIRS, extensions, exclusions)
    if not files:
        pytest.skip("No frontend files found in web/ or frontend/")

    violations: List[Violation] = []
    for f in files:
        violations.extend(check_xss_patterns(f, patterns, REPO_ROOT))

    ratchet_baseline.assert_no_regression(
        validator_id="frontend_security_patterns",
        current_count=len(violations),
        violations=violations,
    )
