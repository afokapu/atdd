"""
URN Spec V3 validators for test headers, reserved slugs, and Phase/Layer validation.

Covers:
- SPEC-V3-001: One test: URN per test file
- SPEC-V3-002: Acceptance vs journey header mutual exclusion
- SPEC-V3-003: Phase and Layer value validation
- SPEC-V3-004: Journey tests must include Train: header
- SPEC-V3-005: Reserved slug enforcement (wagon, train, trains)
- SPEC-V3-006: Tested-By enforcement for production components
- SPEC-V3-007: Train infrastructure components must use assembly layer
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.graph.resolver import TestResolver


REPO_ROOT = find_repo_root()

# Directories to scan for test files
TEST_SCAN_DIRS = [
    REPO_ROOT / "python",
    REPO_ROOT / "supabase",
    REPO_ROOT / "web" / "tests",
    REPO_ROOT / "e2e",
]

# Test file patterns
_TEST_FILE_PATTERNS = [
    re.compile(r"^test_.*\.py$"),
    re.compile(r"^.*_test\.py$"),
    re.compile(r"^.*_test\.dart$"),
    re.compile(r"^.*\.test\.tsx?$"),
    re.compile(r"^.*\.spec\.ts$"),
]

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".dart_tool",
    "build", ".pub-cache", "dist", ".next", ".nuxt", "coverage",
    ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
}

_URN_COMMENT_RE = re.compile(r"(?:#|//)\s*[Uu][Rr][Nn]:\s*([^\s]+)")

# Production code directories for Tested-By scanning (S10 R1 scope)
_PROD_SCAN_DIRS = [
    REPO_ROOT / "python",
    REPO_ROOT / "web",
    REPO_ROOT / "supabase" / "functions",
]

_PROD_EXTENSIONS = {".py", ".dart", ".ts", ".tsx"}

# Patterns to identify test files (excluded from production scan)
_TEST_FILENAME_RE = re.compile(
    r"(^test_.*\.py$|.*_test\.py$|.*_test\.dart$|.*\.test\.tsx?$|.*\.spec\.ts$)"
)

# Patterns for Tested-By header parsing
_TESTED_BY_HEADER_RE = re.compile(r"(?:#|//)\s*[Tt]ested-[Bb]y:")
_TESTED_BY_ENTRY_RE = re.compile(r"(?:#|//)\s*-\s*(test:[^\s]+)")


def _iter_test_files():
    """Yield all test files across scan directories."""
    import os
    for scan_dir in TEST_SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(scan_dir):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                if any(p.match(fname) for p in _TEST_FILE_PATTERNS):
                    yield Path(dirpath) / fname


def _count_test_urns(content: str) -> int:
    """Count the number of test: URN declarations in file content."""
    count = 0
    for line in content.split("\n"):
        m = _URN_COMMENT_RE.search(line)
        if m and m.group(1).startswith("test:"):
            count += 1
    return count


@pytest.mark.platform
def test_v3_one_test_urn_per_file():
    """
    SPEC-V3-001: Every test file must include exactly one test: URN.

    Per URN Spec V3 S9.4: Every test file must include exactly one
    test: URN (file-level identity even if multiple test cases exist).
    """
    violations = []

    for test_file in _iter_test_files():
        try:
            content = test_file.read_text(encoding="utf-8")
        except Exception:
            continue

        count = _count_test_urns(content)
        if count == 0:
            rel = test_file.relative_to(REPO_ROOT)
            violations.append(f"{rel}: missing test: URN (exactly 1 required)")
            continue
        if count > 1:
            rel = test_file.relative_to(REPO_ROOT)
            violations.append(f"{rel}: has {count} test: URNs (must be exactly 1)")
            continue

        # Validate test URN format (must be acceptance or journey, not legacy)
        header = TestResolver.parse_test_header(content)
        if header["test_urn"] and header["format"] == "legacy":
            rel = test_file.relative_to(REPO_ROOT)
            violations.append(
                f"{rel}: legacy test URN format '{header['test_urn']}' — "
                f"must use V3 acceptance (test:{{wagon}}:{{feature}}:...) "
                f"or journey (test:train:{{train_id}}:...) format"
            )

    if violations:
        pytest.fail(
            f"\nSPEC-V3-001: Exactly one test: URN per file. "
            f"Found {len(violations)} violations:\n  "
            + "\n  ".join(violations)
        )


@pytest.mark.platform
def test_v3_acceptance_journey_mutual_exclusion():
    """
    SPEC-V3-002: Acceptance and journey headers are mutually exclusive.

    Per URN Spec V3 S9.4:
    - Acceptance tests: MUST include Acceptance: and WMBT:, MUST NOT have Train:
    - Journey tests: MUST include Train:, MUST NOT have Acceptance: or WMBT:
    """
    violations = []

    for test_file in _iter_test_files():
        try:
            content = test_file.read_text(encoding="utf-8")
        except Exception:
            continue

        header = TestResolver.parse_test_header(content)
        if not header["test_urn"]:
            continue  # No V3 header, skip

        fmt = header["format"]
        rel = test_file.relative_to(REPO_ROOT)

        if fmt == "acceptance":
            if header["train"]:
                violations.append(
                    f"{rel}: acceptance test has Train: header (forbidden)"
                )
            if not header["acceptance"]:
                violations.append(
                    f"{rel}: acceptance test missing Acceptance: header"
                )
            if not header["wmbt"]:
                violations.append(
                    f"{rel}: acceptance test missing WMBT: header"
                )

        elif fmt == "journey":
            if not header["train"]:
                violations.append(
                    f"{rel}: journey test missing Train: header"
                )
            if header["acceptance"]:
                violations.append(
                    f"{rel}: journey test has Acceptance: header (forbidden)"
                )
            if header["wmbt"]:
                violations.append(
                    f"{rel}: journey test has WMBT: header (forbidden)"
                )

    if violations:
        pytest.fail(
            f"\nSPEC-V3-002: Acceptance/journey header mutual exclusion. "
            f"Found {len(violations)} violations:\n  "
            + "\n  ".join(violations)
        )


@pytest.mark.platform
def test_v3_phase_and_layer_values():
    """
    SPEC-V3-003: Phase and Layer must be valid enum values.

    Per URN Spec V3 S10 R12,13:
    - Phase: RED | GREEN | REFACTOR
    - Layer: presentation | application | domain | integration | assembly
    """
    violations = []

    for test_file in _iter_test_files():
        try:
            content = test_file.read_text(encoding="utf-8")
        except Exception:
            continue

        header = TestResolver.parse_test_header(content)
        if not header["test_urn"]:
            continue

        rel = test_file.relative_to(REPO_ROOT)

        if not header["phase"]:
            violations.append(
                f"{rel}: missing Phase: header (required)"
            )
        elif header["phase"] not in TestResolver.VALID_PHASES:
            violations.append(
                f"{rel}: Phase '{header['phase']}' not in {TestResolver.VALID_PHASES}"
            )

        if not header["layer"]:
            violations.append(
                f"{rel}: missing Layer: header (required)"
            )
        elif header["layer"] not in TestResolver.VALID_TEST_LAYERS:
            violations.append(
                f"{rel}: Layer '{header['layer']}' not in {TestResolver.VALID_TEST_LAYERS}"
            )

    if violations:
        pytest.fail(
            f"\nSPEC-V3-003: Invalid Phase/Layer values. "
            f"Found {len(violations)} violations:\n  "
            + "\n  ".join(violations)
        )


@pytest.mark.platform
def test_v3_journey_tests_have_train_header():
    """
    SPEC-V3-004: E2E journey tests must include Train: header.

    Per URN Spec V3 S9.2: Journey tests (test:train:...) must include
    a Train: header with a valid train URN.
    """
    violations = []

    for test_file in _iter_test_files():
        try:
            content = test_file.read_text(encoding="utf-8")
        except Exception:
            continue

        header = TestResolver.parse_test_header(content)
        if not header["test_urn"]:
            continue

        if header["format"] == "journey":
            rel = test_file.relative_to(REPO_ROOT)
            if not header["train"]:
                violations.append(f"{rel}: journey test URN but no Train: header")
            elif not re.match(r"^train:\d{4}-[a-z0-9][a-z0-9-]*$", header["train"]):
                violations.append(
                    f"{rel}: Train: value '{header['train']}' is not a valid "
                    f"train URN (expected train:NNNN-kebab-case)"
                )

    if violations:
        pytest.fail(
            f"\nSPEC-V3-004: Journey tests need Train: header. "
            f"Found {len(violations)} violations:\n  "
            + "\n  ".join(violations)
        )


@pytest.mark.platform
def test_v3_reserved_slugs():
    """
    SPEC-V3-005: Forbid reserved slugs in wagon/feature URNs.

    Per URN Spec V3 S10 R9,10:
    - Feature slug 'wagon' is reserved for wagon entrypoints
    - Wagon slugs 'train' and 'trains' are reserved for train infrastructure
    - Wagon slug 'commons' is reserved for shared infrastructure
    These must not be used as actual wagon or feature plan slugs.
    """
    import yaml

    plan_dir = REPO_ROOT / "plan"
    if not plan_dir.exists():
        pytest.skip("No plan directory")

    violations = []

    # Check wagon manifests for reserved wagon slugs
    for manifest in plan_dir.rglob("_*.yaml"):
        try:
            with open(manifest, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data or not isinstance(data, dict):
                continue
            wagon_slug = data.get("wagon")
            if wagon_slug in ("train", "trains", "commons"):
                violations.append(
                    f"{manifest.relative_to(REPO_ROOT)}: wagon slug '{wagon_slug}' is reserved"
                )
        except Exception:
            continue

    # Check feature files for reserved feature slug 'wagon'
    for feature_file in plan_dir.rglob("features/*.yaml"):
        try:
            with open(feature_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data or not isinstance(data, dict):
                continue
            feature_urn = data.get("urn", "")
            if feature_urn.startswith("feature:"):
                parts = feature_urn.replace("feature:", "").split(":")
                if len(parts) >= 2 and parts[1] == "wagon":
                    violations.append(
                        f"{feature_file.relative_to(REPO_ROOT)}: "
                        f"feature slug 'wagon' is reserved for wagon entrypoints"
                    )
        except Exception:
            continue

    if violations:
        pytest.fail(
            f"\nSPEC-V3-005: Reserved slug violations. "
            f"Found {len(violations)} violations:\n  "
            + "\n  ".join(violations)
        )


def _is_import_only(content: str) -> bool:
    """Check if a Python file is empty or import-only (no logic)."""
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if stripped.startswith(("import ", "from ", "__all__")):
            continue
        # Any other statement means the file contains logic
        return False
    return True


def _iter_production_files():
    """Yield production code files (excluding tests, migrations, generated)."""
    import os
    for scan_dir in _PROD_SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(scan_dir):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            # Skip migration directories
            if "migrations" in Path(dirpath).parts:
                continue
            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix not in _PROD_EXTENSIONS:
                    continue
                # Exclude test files
                if _TEST_FILENAME_RE.match(fname):
                    continue
                # Exclude conftest.py
                if fname == "conftest.py":
                    continue
                yield fpath


def _parse_component_header(content: str) -> dict:
    """Parse component URN and Tested-By entries from a production file header."""
    result = {"component_urn": None, "tested_by": []}
    in_tested_by = False

    for line in content.split("\n"):
        # Component URN
        m = _URN_COMMENT_RE.search(line)
        if m and m.group(1).startswith("component:"):
            result["component_urn"] = m.group(1)
            continue

        # Tested-By header
        if _TESTED_BY_HEADER_RE.search(line):
            in_tested_by = True
            continue

        # Tested-By entries (must follow Tested-By: header)
        if in_tested_by:
            m = _TESTED_BY_ENTRY_RE.search(line)
            if m:
                result["tested_by"].append(m.group(1))
            elif line.strip() and not line.strip().startswith(("#", "//")):
                # Non-comment, non-empty line ends the Tested-By block
                in_tested_by = False

    return result


def _build_train_wagon_index() -> dict:
    """Build a mapping of train_id -> set of wagon slugs from train plan YAMLs.

    Reads plan/_trains/*.yaml and extracts wagon participants from each train.
    Returns empty dict if no train plans exist yet.
    """
    import yaml

    trains_dir = REPO_ROOT / "plan" / "_trains"
    if not trains_dir.exists():
        return {}

    index: Dict[str, set] = {}
    for train_file in trains_dir.glob("*.yaml"):
        try:
            with open(train_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data or not isinstance(data, dict):
                continue

            train_id = data.get("id") or train_file.stem
            wagons = set()
            for wagon_ref in data.get("wagons", []):
                if isinstance(wagon_ref, str):
                    slug = wagon_ref.replace("wagon:", "") if wagon_ref.startswith("wagon:") else wagon_ref
                    wagons.add(slug)
                elif isinstance(wagon_ref, dict):
                    slug = wagon_ref.get("wagon") or wagon_ref.get("slug")
                    if slug:
                        wagons.add(slug.replace("wagon:", "") if slug.startswith("wagon:") else slug)
            if wagons:
                index[train_id] = wagons
        except Exception:
            continue

    return index


def _build_test_urn_index() -> set:
    """Build a set of all test: URNs found in test file headers."""
    test_urns = set()
    for test_file in _iter_test_files():
        try:
            content = test_file.read_text(encoding="utf-8")
        except Exception:
            continue
        for line in content.split("\n"):
            m = _URN_COMMENT_RE.search(line)
            if m and m.group(1).startswith("test:"):
                test_urns.add(m.group(1))
                break  # One test URN per file
    return test_urns


@pytest.mark.platform
def test_v3_components_have_tested_by():
    """
    SPEC-V3-006: Production components must declare Tested-By with valid test URNs.

    Per URN Spec V3 S9.5, S10 R8:
    - Every production component with a component: URN must include a Tested-By header
    - Each test: URN in Tested-By must resolve to an actual test file header
    - Chain alignment: acceptance tests must match component wagon/feature;
      journey tests must reference a train whose participants include the component wagon
    - During migration: warn-only for missing Tested-By and chain mismatches, fail for broken references
    """
    warnings = []
    broken_refs = []
    chain_warnings = []

    # Build index of all known test: URNs for reference validation
    known_test_urns = _build_test_urn_index()

    # Build train -> wagons index for journey chain alignment (S9.5)
    train_wagon_index = _build_train_wagon_index()

    for prod_file in _iter_production_files():
        try:
            content = prod_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Skip __init__.py that are empty/import-only (S10 production code scope)
        if prod_file.name == "__init__.py" and _is_import_only(content):
            continue

        header = _parse_component_header(content)
        if not header["component_urn"]:
            continue  # No component URN, skip (covered by separate validator)

        rel = prod_file.relative_to(REPO_ROOT)

        if not header["tested_by"]:
            # Migration: warn-only for missing Tested-By
            warnings.append(
                f"{rel}: component {header['component_urn']} missing Tested-By header"
            )
            continue

        # Parse component wagon/feature for chain alignment (S9.5)
        comp_parts = header["component_urn"].split(":")
        comp_wagon = comp_parts[1] if len(comp_parts) > 2 else None
        comp_feature = comp_parts[2] if len(comp_parts) > 3 else None

        # Validate each Tested-By reference exists and chain alignment
        for test_ref in header["tested_by"]:
            if test_ref not in known_test_urns:
                broken_refs.append(
                    f"{rel}: Tested-By reference '{test_ref}' not found in any test file"
                )
                continue

            # Chain alignment check (S9.5)
            if comp_wagon == "trains":
                pass  # Reserved wagon 'trains': skip chain validation
            elif test_ref.startswith("test:train:"):
                # Journey chain: component's wagon must be a participant in the train
                # test:train:{train_id}:{harness}-{seq}-{slug}
                train_parts = test_ref.split(":")
                train_id = train_parts[2] if len(train_parts) > 3 else None
                if train_id and train_wagon_index:
                    train_wagons = train_wagon_index.get(train_id)
                    if train_wagons is not None and comp_wagon not in train_wagons:
                        chain_warnings.append(
                            f"{rel}: component {header['component_urn']} Tested-By "
                            f"'{test_ref}' journey chain mismatch — wagon "
                            f"'{comp_wagon}' not in train '{train_id}' participants"
                        )
                elif train_id and not train_wagon_index:
                    # No train plan YAMLs available — cannot validate
                    pass
            else:
                test_parts = test_ref.split(":")
                test_wagon = test_parts[1] if len(test_parts) > 2 else None
                test_feature = test_parts[2] if len(test_parts) > 3 else None
                if comp_wagon and test_wagon and (
                    test_wagon != comp_wagon or test_feature != comp_feature
                ):
                    chain_warnings.append(
                        f"{rel}: component {header['component_urn']} Tested-By "
                        f"'{test_ref}' chain mismatch — expected wagon={comp_wagon}, "
                        f"feature={comp_feature}"
                    )

    # Print warnings (migration: don't fail)
    if warnings:
        print(
            f"\nSPEC-V3-006 MIGRATION WARNINGS: {len(warnings)} components "
            f"missing Tested-By header (warn-only during migration):\n  "
            + "\n  ".join(warnings[:20])
        )
        if len(warnings) > 20:
            print(f"  ... and {len(warnings) - 20} more")

    # Print chain alignment warnings (migration: warn-only per S9.5)
    if chain_warnings:
        print(
            f"\nSPEC-V3-006 CHAIN WARNINGS: {len(chain_warnings)} Tested-By references "
            f"with wagon/feature chain mismatch (warn-only during migration):\n  "
            + "\n  ".join(chain_warnings[:20])
        )
        if len(chain_warnings) > 20:
            print(f"  ... and {len(chain_warnings) - 20} more")

    # Fail on broken references (these are always errors)
    if broken_refs:
        pytest.fail(
            f"\nSPEC-V3-006: Tested-By references must resolve to existing tests. "
            f"Found {len(broken_refs)} broken references:\n  "
            + "\n  ".join(broken_refs)
        )


_TRAINS_COMPONENT_RE = re.compile(
    r"^component:trains:[a-z][a-z0-9-]*:[a-zA-Z0-9.]+:"
    r"(frontend|backend|fe|be):"
    r"(presentation|application|domain|integration|assembly)$"
)


@pytest.mark.platform
def test_v3_train_infra_assembly_only():
    """
    SPEC-V3-007: Train infrastructure components must use assembly layer.

    Per URN Spec V3 S6.4: component:trains:* rejects non-assembly layers.
    """
    violations = []

    for prod_file in _iter_production_files():
        try:
            content = prod_file.read_text(encoding="utf-8")
        except Exception:
            continue

        for line in content.split("\n"):
            m = _URN_COMMENT_RE.search(line)
            if not m:
                continue
            urn = m.group(1)
            if not urn.startswith("component:trains:"):
                continue
            # Parse layer from the URN
            match = _TRAINS_COMPONENT_RE.match(urn)
            if match and match.group(2) != "assembly":
                rel = prod_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel}: {urn} uses layer '{match.group(2)}' "
                    f"(train infra components must use 'assembly')"
                )
            break  # Only check first URN per file

    if violations:
        pytest.fail(
            f"\nSPEC-V3-007: Train infra components must be assembly layer. "
            f"Found {len(violations)} violations:\n  "
            + "\n  ".join(violations)
        )
