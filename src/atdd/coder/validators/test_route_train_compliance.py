"""
Test that routes use train components instead of direct page imports.

Validates:
- SPEC-CODER-PAGE-0004: New routes must use TrainView, not direct page component imports

Routes should map to trains via <TrainView trainId={...} />, not directly
import *Page.tsx components. This enforces the train-driven composition
architecture where the FrontendTrainRunner is the composition root.

Convention: src/atdd/coder/conventions/frontend.convention.yaml → train_composition
Config: .atdd/config.yaml → route_train_compliance
"""

import re
import yaml
import pytest
from pathlib import Path
from typing import Dict, List, Tuple

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import load_atdd_config


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()

# Regex to detect page component imports in router files
# Matches: import FooPage from './pages/FooPage'
#          import { FooPage } from '../pages/FooPage'
#          import FooPage from '../../pages/foo/FooPage'
_PAGE_IMPORT_RE = re.compile(
    r"""import\s+(?:\{[^}]*\}|[\w]+)\s+from\s+['"]([^'"]*[Pp]age[^'"]*?)['"]"""
)

# Regex to detect direct page component usage in JSX route elements
# Matches: element={<FooPage />}   component={FooPage}   element: <FooPage>
_PAGE_JSX_RE = re.compile(
    r"""(?:element|component)\s*[:={]\s*<?(\w*Page)\b"""
)

# Regex to detect TrainView usage (the correct pattern)
_TRAIN_VIEW_RE = re.compile(
    r"""<TrainView\b"""
)

_DEFAULT_ROUTER_PATTERNS = [
    "web/src/**/router.ts",
    "web/src/**/router.tsx",
    "web/src/**/routes.ts",
    "web/src/**/routes.tsx",
    "web/src/**/*-routes.ts",
    "web/src/**/*-routes.tsx",
    "web/src/**/App.tsx",
]


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
def _load_route_config() -> Dict:
    """Load route_train_compliance config from .atdd/config.yaml."""
    config = load_atdd_config(REPO_ROOT)
    return config.get("route_train_compliance", {})


def _load_allowlist(rt_config: Dict) -> Dict[str, str]:
    """
    Build path→migration map from allowlist.

    Existing routes using pages get allowlist treatment (warning).
    New routes using pages are hard failures.
    """
    allowlist = {}
    for entry in rt_config.get("allowlist", []):
        path = entry.get("path", "")
        migration = entry.get("migration", "")
        if path:
            allowlist[path] = migration
    return allowlist


# ---------------------------------------------------------------------------
# Router file discovery
# ---------------------------------------------------------------------------
def _find_router_files(router_patterns: List[str]) -> List[Path]:
    """
    Find router configuration files matching configured glob patterns.

    Falls back to default patterns if none configured.
    """
    files: List[Path] = []
    seen: set = set()

    for pattern in router_patterns:
        for match in REPO_ROOT.glob(pattern):
            if match.is_file() and match not in seen:
                seen.add(match)
                files.append(match)

    return sorted(files)


# ---------------------------------------------------------------------------
# Route analysis
# ---------------------------------------------------------------------------
def _analyze_router_file(
    file_path: Path,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Analyze a router file for page imports and TrainView usage.

    Returns:
        (page_violations, train_usages)
        page_violations: list of dicts with line, import_path, component info
        train_usages: list of dicts with line info
    """
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            content = fh.read()
            lines = content.splitlines()
    except (OSError, UnicodeDecodeError):
        return [], []

    page_violations: List[Dict] = []
    train_usages: List[Dict] = []

    for line_num, line in enumerate(lines, start=1):
        # Check for page imports
        import_match = _PAGE_IMPORT_RE.search(line)
        if import_match:
            import_path = import_match.group(1)
            page_violations.append({
                "line": line_num,
                "import_path": import_path,
                "text": line.strip(),
            })

        # Check for direct page component usage in JSX
        jsx_match = _PAGE_JSX_RE.search(line)
        if jsx_match:
            component = jsx_match.group(1)
            page_violations.append({
                "line": line_num,
                "component": component,
                "text": line.strip(),
            })

        # Track TrainView usage
        if _TRAIN_VIEW_RE.search(line):
            train_usages.append({
                "line": line_num,
                "text": line.strip(),
            })

    return page_violations, train_usages


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------
@pytest.mark.coder
def test_routes_use_train_components():
    """
    SPEC-CODER-PAGE-0004: Routes must use TrainView, not direct page imports.

    Router files should use <TrainView trainId={...} /> to compose wagon
    presentations via the FrontendTrainRunner. Direct imports of *Page.tsx
    components bypass train composition.

    Existing routes in the allowlist produce warnings. New routes using
    pages are hard failures.

    Given: Router configuration files
    When: Scanning for page component imports and JSX usage
    Then: Direct page imports not in allowlist are hard failures
    """
    rt_config = _load_route_config()
    router_patterns = rt_config.get("router_patterns", _DEFAULT_ROUTER_PATTERNS)
    allowlist = _load_allowlist(rt_config)

    router_files = _find_router_files(router_patterns)

    if not router_files:
        pytest.skip(
            "No router files found matching configured patterns. "
            "Configure route_train_compliance.router_patterns in .atdd/config.yaml"
        )

    hard_failures: List[str] = []
    warnings: List[str] = []

    for router_file in router_files:
        rel_path = str(router_file.relative_to(REPO_ROOT))
        page_violations, train_usages = _analyze_router_file(router_file)

        if not page_violations:
            continue

        # Deduplicate by line number
        seen_lines: set = set()

        for violation in page_violations:
            line = violation["line"]
            if line in seen_lines:
                continue
            seen_lines.add(line)

            import_path = violation.get("import_path", "")
            component = violation.get("component", "")
            identifier = import_path or component
            text = violation["text"]

            if rel_path in allowlist:
                warnings.append(
                    f"  SPEC-CODER-PAGE-0004 WARN: Allowlisted route uses page component\n"
                    f"    File:      {rel_path}:{line}\n"
                    f"    Component: {identifier}\n"
                    f"    Code:      {text}\n"
                    f"    Migration: {allowlist[rel_path] or '<missing>'}"
                )
            else:
                hard_failures.append(
                    f"  SPEC-CODER-PAGE-0004 FAIL: Route uses page component instead of train\n"
                    f"    File:      {rel_path}:{line}\n"
                    f"    Component: {identifier}\n"
                    f"    Code:      {text}\n"
                    f"    Fix:       Use <TrainView trainId={{...}} /> instead.\n"
                    f"               See: frontend.convention.yaml → train_composition"
                )

    # Log warnings but don't fail for allowlisted routes
    if warnings:
        for w in warnings:
            print(f"\n{w}")

    if hard_failures:
        pytest.fail(
            f"\n\n{len(hard_failures)} route(s) using direct page components "
            f"(not TrainView):\n\n"
            + "\n\n".join(hard_failures)
            + (f"\n\n({len(warnings)} allowlisted route warning(s) also logged)"
               if warnings else "")
        )


@pytest.mark.coder
def test_route_allowlist_entries_have_migration():
    """
    SPEC-CODER-PAGE-0004 (allowlist hygiene): Every route allowlist entry
    must reference a migration issue.

    Given: route_train_compliance.allowlist in .atdd/config.yaml
    When: Checking each entry for migration field
    Then: Entries missing migration references fail
    """
    rt_config = _load_route_config()
    allowlist_entries = rt_config.get("allowlist", [])

    if not allowlist_entries:
        pytest.skip("No route_train_compliance.allowlist entries in .atdd/config.yaml")

    violations: List[str] = []

    for entry in allowlist_entries:
        path = entry.get("path", "<missing path>")
        migration = entry.get("migration", "")

        if not migration or not migration.strip():
            violations.append(
                f"  SPEC-CODER-PAGE-0004 FAIL: Route allowlist entry missing migration reference\n"
                f"    Path: {path}\n"
                f"    Fix:  Add migration: \"owner/repo#NNN\" to the allowlist entry."
            )

    if violations:
        pytest.fail(
            f"\n\n{len(violations)} route allowlist entry/entries missing migration reference:\n\n"
            + "\n\n".join(violations)
        )
