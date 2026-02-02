"""
Session archive status validation.

Validates archive placement aligns with session status:
1. COMPLETE sessions should be in archive/ (warning)
2. Sessions in archive/ should be COMPLETE or OBSOLETE (warning)

These are warnings, not failures, to allow migration flexibility.

Convention: src/atdd/coach/conventions/session.convention.yaml
Config: .atdd/config.yaml (coach.archive_status_warnings)

Run: atdd validate coach
"""
import pytest
import yaml
import fnmatch
from pathlib import Path
from typing import Dict, List, Any, Optional

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import load_atdd_config


# ============================================================================
# Configuration
# ============================================================================

REPO_ROOT = find_repo_root()
SESSIONS_DIR = REPO_ROOT / "atdd-sessions"
ARCHIVE_DIR = SESSIONS_DIR / "archive"

# Terminal statuses that should be archived
ARCHIVABLE_STATUSES = {"COMPLETE", "OBSOLETE"}


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def config() -> Dict[str, Any]:
    """Load ATDD configuration."""
    return load_atdd_config(REPO_ROOT)


@pytest.fixture
def archive_warnings_enabled(config: Dict[str, Any]) -> bool:
    """Check if archive status warnings are enabled."""
    return config.get("coach", {}).get("archive_status_warnings", True)


@pytest.fixture
def session_files() -> List[Path]:
    """Get all session files in main directory (not archive)."""
    if not SESSIONS_DIR.exists():
        return []

    return sorted([
        f for f in SESSIONS_DIR.glob("SESSION-*.md")
        if f.name != "SESSION-TEMPLATE.md"
    ])


@pytest.fixture
def archived_files() -> List[Path]:
    """Get all session files in archive directory."""
    if not ARCHIVE_DIR.exists():
        return []

    return sorted(ARCHIVE_DIR.glob("SESSION-*.md"))


def parse_session_status(path: Path) -> Optional[str]:
    """Parse status from session file frontmatter."""
    content = path.read_text()

    if not content.startswith("---"):
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        frontmatter = yaml.safe_load(parts[1])
        status = str(frontmatter.get("status", "")).upper()
        # Handle status with extra info (e.g., "ACTIVE - working")
        return status.split()[0] if status else None
    except yaml.YAMLError:
        return None


# ============================================================================
# Archive Status Validation Tests
# ============================================================================

@pytest.mark.coach
def test_complete_sessions_should_be_archived(
    session_files: List[Path],
    archive_warnings_enabled: bool
):
    """
    SPEC-COACH-ARCHIVE-001: COMPLETE sessions should be in archive/

    Given: Session files in main directory
    When: Checking status
    Then: Sessions with COMPLETE/OBSOLETE status should be in archive/

    Note: This is a warning, not a failure, to allow migration flexibility.
    """
    if not archive_warnings_enabled:
        pytest.skip("Archive status warnings disabled in config")

    if not session_files:
        pytest.skip("No session files found")

    should_archive = []

    for path in session_files:
        status = parse_session_status(path)
        if status in ARCHIVABLE_STATUSES:
            should_archive.append(f"{path.name} (status: {status})")

    if should_archive:
        print(
            f"\n⚠️  Found {len(should_archive)} completed sessions not in archive/:\n" +
            "\n".join(f"  - {s}" for s in should_archive) +
            "\n\nConsider running 'atdd session archive <id>' to move them."
        )


@pytest.mark.coach
def test_archived_sessions_should_be_complete(
    archived_files: List[Path],
    archive_warnings_enabled: bool
):
    """
    SPEC-COACH-ARCHIVE-002: Archived sessions should have COMPLETE/OBSOLETE status

    Given: Session files in archive/ directory
    When: Checking status
    Then: All archived sessions should have terminal status

    Note: This is a warning, not a failure, to allow migration flexibility.
    """
    if not archive_warnings_enabled:
        pytest.skip("Archive status warnings disabled in config")

    if not archived_files:
        pytest.skip("No archived session files found")

    not_complete = []

    for path in archived_files:
        status = parse_session_status(path)
        if status and status not in ARCHIVABLE_STATUSES:
            not_complete.append(f"{path.name} (status: {status})")

    if not_complete:
        print(
            f"\n⚠️  Found {len(not_complete)} archived sessions without terminal status:\n" +
            "\n".join(f"  - {s}" for s in not_complete) +
            "\n\nEither update status to COMPLETE/OBSOLETE or move back to atdd-sessions/."
        )


@pytest.mark.coach
def test_archive_directory_structure():
    """
    SPEC-COACH-ARCHIVE-003: Archive directory exists if sessions directory exists

    Given: atdd-sessions/ directory exists
    When: Checking for archive/ subdirectory
    Then: archive/ directory should exist (create if missing)
    """
    if not SESSIONS_DIR.exists():
        pytest.skip("Sessions directory not found")

    if not ARCHIVE_DIR.exists():
        print(
            f"\n⚠️  Archive directory does not exist: {ARCHIVE_DIR}\n"
            "Consider creating it: mkdir -p atdd-sessions/archive/"
        )


# ============================================================================
# Stale Session Detection
# ============================================================================

@pytest.mark.coach
def test_stale_active_sessions(session_files: List[Path]):
    """
    SPEC-COACH-ARCHIVE-004: Detect potentially stale ACTIVE sessions

    Given: Session files with ACTIVE status
    When: Checking file modification time
    Then: Warn about sessions not modified in 7+ days
    """
    if not session_files:
        pytest.skip("No session files found")

    from datetime import datetime, timedelta

    stale_threshold = timedelta(days=7)
    now = datetime.now()
    stale = []

    for path in session_files:
        status = parse_session_status(path)
        if status != "ACTIVE":
            continue

        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        age = now - mtime

        if age > stale_threshold:
            days = age.days
            stale.append(f"{path.name} (last modified {days} days ago)")

    if stale:
        print(
            f"\n⚠️  Found {len(stale)} potentially stale ACTIVE sessions:\n" +
            "\n".join(f"  - {s}" for s in stale) +
            "\n\nConsider updating status to BLOCKED, COMPLETE, or OBSOLETE."
        )


@pytest.mark.coach
def test_blocked_sessions_have_reason(session_files: List[Path]):
    """
    SPEC-COACH-ARCHIVE-005: BLOCKED sessions should document reason

    Given: Session files with BLOCKED status
    When: Checking session log
    Then: Most recent log entry should explain the blocker
    """
    if not session_files:
        pytest.skip("No session files found")

    import re

    missing_reason = []

    for path in session_files:
        status = parse_session_status(path)
        if status != "BLOCKED":
            continue

        content = path.read_text()

        # Check for Blocked: section in session log
        has_blocked_entry = bool(re.search(
            r"\*\*Blocked:\*\*\s*\n\s*-\s*\S",
            content
        ))

        # Or check frontmatter for blocker field
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1])
                    has_blocked_entry = has_blocked_entry or bool(
                        frontmatter.get("blocker") or
                        frontmatter.get("blocked_by") or
                        frontmatter.get("blocked_reason")
                    )
                except yaml.YAMLError:
                    pass

        if not has_blocked_entry:
            missing_reason.append(path.name)

    if missing_reason:
        print(
            f"\n⚠️  Found {len(missing_reason)} BLOCKED sessions without documented reason:\n" +
            "\n".join(f"  - {m}" for m in missing_reason) +
            "\n\nAdd **Blocked:** entry to Session Log or 'blocker' field to frontmatter."
        )


# ============================================================================
# Summary
# ============================================================================

@pytest.mark.coach
def test_archive_status_summary(
    session_files: List[Path],
    archived_files: List[Path]
):
    """
    Generate archive status summary.

    This test always passes but prints a summary.
    """
    print("\n" + "=" * 60)
    print("SESSION ARCHIVE STATUS SUMMARY")
    print("=" * 60)

    # Count by status in main directory
    main_statuses: Dict[str, int] = {}
    for path in session_files:
        status = parse_session_status(path) or "UNKNOWN"
        main_statuses[status] = main_statuses.get(status, 0) + 1

    # Count by status in archive
    archive_statuses: Dict[str, int] = {}
    for path in archived_files:
        status = parse_session_status(path) or "UNKNOWN"
        archive_statuses[status] = archive_statuses.get(status, 0) + 1

    print(f"\nMain directory ({len(session_files)} files):")
    for status, count in sorted(main_statuses.items()):
        marker = "⚠️ " if status in ARCHIVABLE_STATUSES else "   "
        print(f"  {marker}{status}: {count}")

    print(f"\nArchive directory ({len(archived_files)} files):")
    for status, count in sorted(archive_statuses.items()):
        marker = "⚠️ " if status not in ARCHIVABLE_STATUSES else "   "
        print(f"  {marker}{status}: {count}")

    # Summary advice
    main_archivable = sum(
        main_statuses.get(s, 0) for s in ARCHIVABLE_STATUSES
    )
    archive_active = sum(
        archive_statuses.get(s, 0) for s in archive_statuses
        if s not in ARCHIVABLE_STATUSES
    )

    if main_archivable > 0 or archive_active > 0:
        print("\n⚠️  Recommendations:")
        if main_archivable > 0:
            print(f"   - Archive {main_archivable} completed session(s)")
        if archive_active > 0:
            print(f"   - Review {archive_active} non-terminal archived session(s)")

    print("\n" + "=" * 60)
