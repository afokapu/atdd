"""
Test GSAP layer usage enforcement.

GSAP is approved for frontend animation but must be constrained to the presentation layer
to preserve layer purity and prevent architectural drift.

Convention: atdd/coder/conventions/technology.convention.yaml (Section 7.1)
Spec: GSAP Stack Integration Spec (ATDD) v1.1

Allowed GSAP paths:
  - web/src/{wagon}/{feature}/presentation/**

Forbidden GSAP paths:
  - web/src/{wagon}/{feature}/domain/**
  - web/src/{wagon}/{feature}/application/**
  - web/src/{wagon}/{feature}/integration/**
  - web/src/commons/** (unless commons adds a presentation layer)
"""

import pytest
import re
from pathlib import Path
from typing import List, Tuple, Optional

from atdd.coach.utils.repo import find_repo_root


REPO_ROOT = find_repo_root()
WEB_SRC = REPO_ROOT / "web" / "src"

# GSAP import detection patterns per Section 6 of the spec
GSAP_IMPORT_PATTERNS = [
    # ESM imports: import ... from "gsap" or 'gsap'
    r'''import\s+.*?\s+from\s+["']gsap["']''',
    r'''import\s+.*?\s+from\s+["']gsap/[^"']+["']''',
    r'''import\s+.*?\s+from\s+["']@gsap/[^"']+["']''',

    # Type-only imports (also forbidden outside presentation)
    r'''import\s+type\s+.*?\s+from\s+["']gsap["']''',
    r'''import\s+type\s+.*?\s+from\s+["']gsap/[^"']+["']''',
    r'''import\s+type\s+.*?\s+from\s+["']@gsap/[^"']+["']''',

    # Dynamic imports
    r'''import\s*\(\s*["']gsap["']\s*\)''',
    r'''import\s*\(\s*["']gsap/[^"']+["']\s*\)''',
    r'''import\s*\(\s*["']@gsap/[^"']+["']\s*\)''',

    # CJS require
    r'''require\s*\(\s*["']gsap["']\s*\)''',
    r'''require\s*\(\s*["']gsap/[^"']+["']\s*\)''',
    r'''require\s*\(\s*["']@gsap/[^"']+["']\s*\)''',
]

# Compile patterns for efficiency
GSAP_PATTERNS_COMPILED = [re.compile(p, re.MULTILINE) for p in GSAP_IMPORT_PATTERNS]


def _is_presentation_layer(file_path: Path) -> bool:
    """
    Check if a file is in the presentation layer.

    Valid presentation paths:
      - web/src/{wagon}/{feature}/presentation/**
      - web/tests/{wagon}/{feature}/presentation/** (if tests allowlist enabled)

    Invalid paths (GSAP forbidden):
      - web/src/{wagon}/{feature}/domain/**
      - web/src/{wagon}/{feature}/application/**
      - web/src/{wagon}/{feature}/integration/**
      - web/src/commons/** (no presentation layer in commons currently)
    """
    try:
        rel_path = file_path.relative_to(WEB_SRC)
    except ValueError:
        return False

    parts = rel_path.parts

    # commons/** is forbidden (no presentation layer)
    if len(parts) > 0 and parts[0] == "commons":
        return False

    # Standard wagon structure: {wagon}/{feature}/{layer}/...
    # Need at least 3 parts: wagon, feature, layer
    if len(parts) >= 3:
        layer = parts[2]
        return layer == "presentation"

    return False


def _find_gsap_import(content: str) -> Optional[str]:
    """
    Check if file content contains GSAP imports.

    Returns the matched import string if found, None otherwise.
    """
    for pattern in GSAP_PATTERNS_COMPILED:
        match = pattern.search(content)
        if match:
            return match.group(0)
    return None


def _scan_files_for_gsap(directory: Path) -> List[Tuple[Path, str]]:
    """
    Scan TypeScript files for GSAP imports.

    Returns list of (file_path, matched_import) tuples for files
    that use GSAP outside the presentation layer.
    """
    violations: List[Tuple[Path, str]] = []

    if not directory.exists():
        return violations

    # Scan .ts and .tsx files
    for ext in ["*.ts", "*.tsx"]:
        for ts_file in directory.rglob(ext):
            try:
                content = ts_file.read_text()
            except Exception:
                continue

            gsap_import = _find_gsap_import(content)
            if gsap_import and not _is_presentation_layer(ts_file):
                violations.append((ts_file, gsap_import))

    return violations


def scan_gsap_layer_usage(repo_root: Path):
    """Scan for GSAP imports outside presentation layer. Used by ratchet baseline."""
    web_src = repo_root / "web" / "src"
    if not web_src.exists():
        return 0, []
    violations = _scan_files_for_gsap(web_src)
    strs = []
    for file_path, matched_import in violations:
        try:
            rel = file_path.relative_to(repo_root)
        except ValueError:
            rel = file_path
        strs.append(f"{rel}: {matched_import}")
    return len(violations), strs


def scan_gsap_commons(repo_root: Path):
    """Scan for GSAP imports in commons. Used by ratchet baseline."""
    commons_dir = repo_root / "web" / "src" / "commons"
    if not commons_dir.exists():
        return 0, []
    violations = []
    for ext in ["*.ts", "*.tsx"]:
        for ts_file in commons_dir.rglob(ext):
            try:
                content = ts_file.read_text()
            except Exception:
                continue
            gsap_import = _find_gsap_import(content)
            if gsap_import:
                try:
                    rel = ts_file.relative_to(repo_root)
                except ValueError:
                    rel = ts_file
                violations.append(f"{rel}: {gsap_import}")
    return len(violations), violations


@pytest.mark.coder
def test_gsap_only_in_presentation_layer(ratchet_baseline):
    """
    SPEC-CODER-GSAP-0001: GSAP imports allowed only in presentation layer.

    GIVEN: All TypeScript files in web/src/
    WHEN: Checking for GSAP imports
    THEN: Violation count does not exceed baseline (ratchet pattern)

    Validates: GSAP is UI-only and constrained to presentation code
    """
    if not WEB_SRC.exists():
        pytest.skip("web/src does not exist")

    count, violations = scan_gsap_layer_usage(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="gsap_layer_usage",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_gsap_not_in_commons(ratchet_baseline):
    """
    SPEC-CODER-GSAP-0002: GSAP imports forbidden in commons.

    GIVEN: All TypeScript files in web/src/commons/
    WHEN: Checking for GSAP imports
    THEN: Violation count does not exceed baseline (ratchet pattern)

    Validates: Domain purity in commons module
    """
    commons_dir = WEB_SRC / "commons"
    if not commons_dir.exists():
        pytest.skip("web/src/commons does not exist")

    count, violations = scan_gsap_commons(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="gsap_commons",
        current_count=count,
        violations=violations,
    )
