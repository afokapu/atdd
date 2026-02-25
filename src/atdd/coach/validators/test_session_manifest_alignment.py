"""
Issue-manifest alignment validation.

Ensures issue files and manifest entries are synchronized:
1. Every manifest entry has a corresponding issue file
2. Every issue file has a manifest entry
3. Status in issue frontmatter matches manifest status

Convention: src/atdd/coach/conventions/issue.convention.yaml
Schema: src/atdd/coach/schemas/manifest.schema.json

Run: atdd validate coach
"""
import pytest
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from atdd.coach.utils.repo import find_repo_root


# ============================================================================
# Configuration
# ============================================================================

REPO_ROOT = find_repo_root()
SESSIONS_DIR = REPO_ROOT / "atdd-sessions"
ARCHIVE_DIR = SESSIONS_DIR / "archive"
MANIFEST_FILE = REPO_ROOT / ".atdd" / "manifest.yaml"

# Valid statuses from convention
VALID_STATUSES = {"INIT", "PLANNED", "ACTIVE", "BLOCKED", "COMPLETE", "OBSOLETE", "UNKNOWN"}


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def manifest() -> Optional[Dict[str, Any]]:
    """Load session manifest from .atdd/manifest.yaml."""
    if not MANIFEST_FILE.exists():
        return None

    with open(MANIFEST_FILE) as f:
        return yaml.safe_load(f)


@pytest.fixture
def session_files() -> List[Path]:
    """Get all session files (excluding template, including archive)."""
    if not SESSIONS_DIR.exists():
        return []

    files = []

    # Main sessions directory
    for f in SESSIONS_DIR.glob("SESSION-*.md"):
        if f.name != "ISSUE-TEMPLATE.md":
            files.append(f)

    # Archive directory
    if ARCHIVE_DIR.exists():
        for f in ARCHIVE_DIR.glob("SESSION-*.md"):
            files.append(f)

    return sorted(files)


def parse_session_frontmatter(path: Path) -> Optional[Dict[str, Any]]:
    """Parse YAML frontmatter from session file."""
    content = path.read_text()

    if not content.startswith("---"):
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        return yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None


def get_session_id_from_filename(filename: str) -> Optional[str]:
    """Extract session ID from filename (e.g., SESSION-01-foo.md -> 01)."""
    import re
    match = re.match(r"SESSION-(\d{2})-", filename)
    return match.group(1) if match else None


# ============================================================================
# Manifest Entry Validation Tests
# ============================================================================

@pytest.mark.coach
def test_manifest_exists():
    """
    SPEC-COACH-MANIFEST-001: Manifest file exists

    Given: Initialized ATDD project
    When: Checking for manifest file
    Then: .atdd/manifest.yaml exists
    """
    if not (REPO_ROOT / ".atdd").exists():
        pytest.skip("ATDD not initialized (no .atdd/ directory)")

    assert MANIFEST_FILE.exists(), \
        f"Manifest file not found at {MANIFEST_FILE}. Run 'atdd init' first."


@pytest.mark.coach
def test_manifest_entries_have_session_files(manifest: Optional[Dict], session_files: List[Path]):
    """
    SPEC-COACH-MANIFEST-002: Every manifest entry has a corresponding session file

    Given: Session manifest with entries
    When: Checking for session files
    Then: Each manifest entry has a matching file on disk
    """
    if manifest is None:
        pytest.skip("No manifest file found")

    sessions_dir = manifest.get("sessions_dir", "atdd-sessions")
    missing = []

    for entry in manifest.get("sessions", []):
        file_path = entry.get("file", "")
        session_id = entry.get("id", "")

        # Resolve full path
        full_path = REPO_ROOT / sessions_dir / file_path

        if not full_path.exists():
            missing.append(f"id={session_id}: {file_path}")

    if missing:
        pytest.fail(
            f"Found {len(missing)} manifest entries without session files:\n" +
            "\n".join(f"  - {m}" for m in missing)
        )


@pytest.mark.coach
def test_session_files_have_manifest_entries(manifest: Optional[Dict], session_files: List[Path]):
    """
    SPEC-COACH-MANIFEST-003: Every session file has a manifest entry

    Given: Session files in atdd-sessions/
    When: Checking manifest entries
    Then: Each session file has a corresponding manifest entry
    """
    if manifest is None:
        pytest.skip("No manifest file found")

    if not session_files:
        pytest.skip("No session files found")

    # Build set of manifest file paths
    sessions_dir = manifest.get("sessions_dir", "atdd-sessions")
    manifest_files = set()

    for entry in manifest.get("sessions", []):
        file_path = entry.get("file", "")
        manifest_files.add(file_path)

    # Check each session file
    orphaned = []

    for session_path in session_files:
        # Compute relative path from sessions_dir
        try:
            rel_path = session_path.relative_to(REPO_ROOT / sessions_dir)
            rel_str = str(rel_path)
        except ValueError:
            rel_str = session_path.name

        if rel_str not in manifest_files:
            orphaned.append(session_path.name)

    if orphaned:
        pytest.fail(
            f"Found {len(orphaned)} session files without manifest entries:\n" +
            "\n".join(f"  - {o}" for o in orphaned) +
            "\n\nRun 'atdd list' to update manifest."
        )


@pytest.mark.coach
def test_manifest_status_matches_session_frontmatter(manifest: Optional[Dict]):
    """
    SPEC-COACH-MANIFEST-004: Manifest status matches session frontmatter status

    Given: Session manifest with status fields
    When: Comparing to session file frontmatter
    Then: Status values match (or warning on mismatch)
    """
    if manifest is None:
        pytest.skip("No manifest file found")

    sessions_dir = manifest.get("sessions_dir", "atdd-sessions")
    mismatches = []

    for entry in manifest.get("sessions", []):
        file_path = entry.get("file", "")
        session_id = entry.get("id", "")
        manifest_status = entry.get("status", "UNKNOWN").upper()

        # Load session file
        full_path = REPO_ROOT / sessions_dir / file_path
        if not full_path.exists():
            continue

        frontmatter = parse_session_frontmatter(full_path)
        if frontmatter is None:
            continue

        # Compare status
        file_status = str(frontmatter.get("status", "UNKNOWN")).upper()
        # Handle status with extra info (e.g., "ACTIVE - working on X")
        file_status_word = file_status.split()[0] if file_status else "UNKNOWN"

        if file_status_word != manifest_status:
            mismatches.append(
                f"SESSION-{session_id}: manifest={manifest_status}, file={file_status_word}"
            )

    if mismatches:
        # Warn but don't fail - mismatches may be intentional during transitions
        print(
            f"\n⚠️  Found {len(mismatches)} status mismatches between manifest and files:\n" +
            "\n".join(f"  - {m}" for m in mismatches) +
            "\n\nRun 'atdd list' to reconcile."
        )


@pytest.mark.coach
def test_manifest_type_matches_session_frontmatter(manifest: Optional[Dict]):
    """
    SPEC-COACH-MANIFEST-005: Manifest type matches session frontmatter type

    Given: Session manifest with type fields
    When: Comparing to session file frontmatter
    Then: Type values match
    """
    if manifest is None:
        pytest.skip("No manifest file found")

    sessions_dir = manifest.get("sessions_dir", "atdd-sessions")
    mismatches = []

    for entry in manifest.get("sessions", []):
        file_path = entry.get("file", "")
        session_id = entry.get("id", "")
        manifest_type = entry.get("type", "unknown").lower()

        # Load session file
        full_path = REPO_ROOT / sessions_dir / file_path
        if not full_path.exists():
            continue

        frontmatter = parse_session_frontmatter(full_path)
        if frontmatter is None:
            continue

        # Compare type
        file_type = str(frontmatter.get("type", "unknown")).lower()

        if file_type != manifest_type:
            mismatches.append(
                f"SESSION-{session_id}: manifest={manifest_type}, file={file_type}"
            )

    if mismatches:
        pytest.fail(
            f"Found {len(mismatches)} type mismatches between manifest and files:\n" +
            "\n".join(f"  - {m}" for m in mismatches)
        )


@pytest.mark.coach
def test_manifest_ids_are_unique(manifest: Optional[Dict]):
    """
    SPEC-COACH-MANIFEST-006: Manifest session IDs are unique

    Given: Session manifest
    When: Checking session IDs
    Then: No duplicate IDs exist
    """
    if manifest is None:
        pytest.skip("No manifest file found")

    ids = {}
    duplicates = []

    for entry in manifest.get("sessions", []):
        session_id = entry.get("id", "")
        file_path = entry.get("file", "")

        if session_id in ids:
            duplicates.append(f"id={session_id}: {ids[session_id]} AND {file_path}")
        else:
            ids[session_id] = file_path

    if duplicates:
        pytest.fail(
            f"Found duplicate session IDs in manifest:\n" +
            "\n".join(f"  - {d}" for d in duplicates)
        )


@pytest.mark.coach
def test_manifest_file_ids_match_filename(manifest: Optional[Dict]):
    """
    SPEC-COACH-MANIFEST-007: Manifest entry ID matches filename

    Given: Session manifest entries
    When: Comparing ID to filename pattern
    Then: Entry ID matches SESSION-{ID}-* in filename
    """
    if manifest is None:
        pytest.skip("No manifest file found")

    mismatches = []

    for entry in manifest.get("sessions", []):
        session_id = entry.get("id", "")
        file_path = entry.get("file", "")

        # Extract ID from filename
        filename = Path(file_path).name
        file_id = get_session_id_from_filename(filename)

        if file_id and file_id != session_id:
            mismatches.append(
                f"id={session_id} but filename has id={file_id}: {file_path}"
            )

    if mismatches:
        pytest.fail(
            f"Found {len(mismatches)} ID mismatches between manifest and filenames:\n" +
            "\n".join(f"  - {m}" for m in mismatches)
        )


# ============================================================================
# Summary
# ============================================================================

@pytest.mark.coach
def test_manifest_alignment_summary(manifest: Optional[Dict], session_files: List[Path]):
    """
    Generate a summary of manifest alignment.

    This test always passes but prints a summary.
    """
    if manifest is None:
        print("\n⚠️  No manifest file found. Run 'atdd init' to create one.")
        return

    manifest_count = len(manifest.get("sessions", []))
    file_count = len(session_files)

    print("\n" + "=" * 60)
    print("SESSION MANIFEST ALIGNMENT SUMMARY")
    print("=" * 60)
    print(f"\nManifest entries: {manifest_count}")
    print(f"Session files:    {file_count}")

    if manifest_count == file_count:
        print("\n✅ Manifest and files are aligned")
    else:
        print(f"\n⚠️  Difference: {abs(manifest_count - file_count)} entries")

    # Status breakdown
    statuses = {}
    for entry in manifest.get("sessions", []):
        status = entry.get("status", "UNKNOWN")
        statuses[status] = statuses.get(status, 0) + 1

    print("\nBy Status:")
    for status, count in sorted(statuses.items()):
        print(f"  {status}: {count}")

    print("\n" + "=" * 60)
