"""
Test for intra-layer code duplication in TypeScript/Preact code.

Validates:
- No structurally identical code fragments (>=5 lines) within same layer
  across different files in web/

Uses regex-based structural normalization (no tree-sitter dependency):
- Strip string literals, numbers, identifiers
- Hash consecutive non-trivial line blocks
- Compare within same architectural layer

Conventions from:
- atdd/coder/conventions/duplication.convention.yaml

Reuses layer detection from test_typescript_architecture.py.
"""

import fnmatch
import hashlib
import os
import re
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
WEB_SRC = REPO_ROOT / "web" / "src"

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
DUPLICATION_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "duplication.convention.yaml"

_SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", ".nuxt",
    "coverage", "__pycache__", ".cache",
}

_TS_EXTENSIONS = {".ts", ".tsx"}


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
# Layer detection (reuses logic from test_typescript_architecture.py)
# ---------------------------------------------------------------------------
def determine_layer_from_path(file_path: Path) -> str:
    """
    Determine architectural layer from TypeScript file path.

    Returns: 'domain', 'application', 'presentation', 'integration', or 'unknown'
    """
    path_str = str(file_path).lower()

    if '/domain/' in path_str:
        return 'domain'
    elif '/application/' in path_str:
        return 'application'
    elif '/presentation/' in path_str:
        return 'presentation'
    elif '/integration/' in path_str or '/infrastructure/' in path_str:
        return 'integration'

    # Alternative patterns
    if '/entities/' in path_str or '/models/' in path_str or '/value_objects/' in path_str:
        return 'domain'
    elif '/use_cases/' in path_str or '/usecases/' in path_str or '/hooks/' in path_str:
        return 'application'
    elif '/components/' in path_str or '/pages/' in path_str or '/views/' in path_str:
        return 'presentation'
    elif '/adapters/' in path_str or '/clients/' in path_str or '/api/' in path_str:
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


def _collect_ts_files(
    base_dir: Path,
    exclusions: Optional[List[str]] = None,
) -> List[Path]:
    """Walk base_dir for *.ts/*.tsx files, honouring skip-dirs and exclusions."""
    if not base_dir.exists():
        return []
    exclusions = exclusions or []
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(base_dir):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if not any(fname.endswith(ext) for ext in _TS_EXTENSIONS):
                continue
            full = Path(dirpath) / fname
            if _matches_exclusion(full, exclusions, base_dir):
                continue
            files.append(full)
    return files


# ---------------------------------------------------------------------------
# Regex-based structural normalization
# ---------------------------------------------------------------------------

# Patterns for normalization (order matters)
_NORMALIZE_PATTERNS = [
    # Remove single-line comments
    (re.compile(r"//.*$", re.MULTILINE), ""),
    # Remove multi-line comments
    (re.compile(r"/\*.*?\*/", re.DOTALL), ""),
    # Replace string literals (single, double, backtick)
    (re.compile(r"'[^']*'"), '"S"'),
    (re.compile(r'"[^"]*"'), '"S"'),
    (re.compile(r"`[^`]*`"), '"S"'),
    # Replace numbers
    (re.compile(r"\b\d+\.?\d*\b"), "0"),
    # Replace identifiers (but preserve keywords and structural tokens)
    (re.compile(
        r"\b(?!(?:import|export|from|const|let|var|function|class|interface|type|"
        r"if|else|for|while|do|switch|case|break|continue|return|throw|try|catch|"
        r"finally|new|delete|typeof|instanceof|void|in|of|as|is|async|await|"
        r"extends|implements|static|get|set|public|private|protected|readonly|"
        r"abstract|override|enum|namespace|module|declare|default|yield|super|"
        r"this|true|false|null|undefined|never|any|string|number|boolean|object|"
        r"unknown|void|Promise|Array|Map|Set|Record)\b)[a-zA-Z_$][a-zA-Z0-9_$]*"
    ), "ID"),
]


def _normalize_line(line: str) -> str:
    """Normalize a TypeScript line to structural form."""
    result = line.strip()
    if not result:
        return ""
    for pattern, replacement in _NORMALIZE_PATTERNS:
        result = pattern.sub(replacement, result)
    # Collapse whitespace
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _is_trivial_line(normalized: str) -> bool:
    """Check if a normalized line is trivial (braces, empty, single tokens)."""
    return normalized in ("", "{", "}", "};", ");", "],", ")", "]", "});", "});")


def extract_ts_fragments(
    file_path: Path,
    min_lines: int,
) -> List[Tuple[str, int, int]]:
    """
    Extract hashable code fragments from a TypeScript file.

    Uses a sliding window of min_lines consecutive non-trivial lines.

    Returns: list of (hash, start_line, end_line)
    """
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = source.splitlines()

    # Build list of (original_lineno, normalized_line) for non-trivial lines
    non_trivial: List[Tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        normalized = _normalize_line(line)
        if not _is_trivial_line(normalized):
            non_trivial.append((i, normalized))

    if len(non_trivial) < min_lines:
        return []

    fragments: List[Tuple[str, int, int]] = []
    for i in range(len(non_trivial) - min_lines + 1):
        window = non_trivial[i:i + min_lines]
        block = "\n".join(line for _, line in window)
        h = hashlib.sha256(block.encode("utf-8")).hexdigest()[:16]
        start_line = window[0][0]
        end_line = window[-1][0]
        fragments.append((h, start_line, end_line))

    return fragments


# ---------------------------------------------------------------------------
# Duplication detection
# ---------------------------------------------------------------------------
def find_intra_layer_duplicates_ts(
    files_by_layer: Dict[str, List[Path]],
    min_lines: int,
) -> List[Dict]:
    """
    Find duplicate code fragments within the same architectural layer.

    Only reports duplicates across DIFFERENT files.

    Returns: list of violation dicts.
    """
    violations: List[Dict] = []

    for layer, files in files_by_layer.items():
        if len(files) < 2:
            continue

        hash_map: Dict[str, List[Tuple[Path, int, int]]] = {}

        for f in files:
            for h, start, end in extract_ts_fragments(f, min_lines):
                hash_map.setdefault(h, []).append((f, start, end))

        for h, locations in hash_map.items():
            unique_files = set(loc[0] for loc in locations)
            if len(unique_files) < 2:
                continue

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
                    "lines": min_lines,
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

def scan_typescript_duplications(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for intra-layer TypeScript duplications. Used by ratchet baseline."""
    convention = load_duplication_convention()
    ts_rule = convention.get("rules", {}).get("intra_layer_duplication_typescript", {})
    min_lines = ts_rule.get("min_fragment_lines", 7)
    exclusions = ts_rule.get("exclusions", [])

    web_src = repo_root / "web" / "src"
    ts_files = _collect_ts_files(web_src, exclusions)
    if not ts_files:
        return 0, []

    files_by_layer: Dict[str, List[Path]] = {}
    for f in ts_files:
        layer = determine_layer_from_path(f)
        if layer == "unknown":
            continue
        files_by_layer.setdefault(layer, []).append(f)

    violations = find_intra_layer_duplicates_ts(files_by_layer, min_lines)
    violation_strs = []
    for v in violations:
        try:
            rel_a = v["file_a"].relative_to(repo_root)
        except ValueError:
            rel_a = v["file_a"]
        try:
            rel_b = v["file_b"].relative_to(repo_root)
        except ValueError:
            rel_b = v["file_b"]
        violation_strs.append(
            f"[{v['layer']}] {rel_a}:{v['line_a']} ↔ {rel_b}:{v['line_b']} "
            f"({v['lines']} identical normalized lines)"
        )
    return len(violations), violation_strs


@pytest.mark.coder
def test_no_intra_layer_duplication_typescript(ratchet_baseline):
    """
    SPEC-CODER-DUP-0002: No structurally identical TypeScript fragments within same layer.

    Regex-based structural normalization detects copy-paste code across
    different files in the same architectural layer under web/src/.
    Identifiers and literals are normalized so renamed copies are caught.

    Given: TypeScript files in web/src/ grouped by architectural layer
    When: Extracting normalized line fragments and comparing hashes within each layer
    Then: Violation count does not exceed baseline (ratchet pattern)

    Convention: atdd/coder/conventions/duplication.convention.yaml
    """
    ts_files = _collect_ts_files(WEB_SRC)
    if not ts_files:
        pytest.skip("No TypeScript files found in web/src/ to validate")

    count, violations = scan_typescript_duplications(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="duplication_detector_typescript",
        current_count=count,
        violations=violations,
    )
