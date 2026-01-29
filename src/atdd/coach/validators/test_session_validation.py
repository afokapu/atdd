"""
Session file validation against session.convention.yaml.

Purpose: Validate session files before implementation starts, after design/planning phase.
Convention: src/atdd/coach/conventions/session.convention.yaml
Template: src/atdd/coach/templates/SESSION-TEMPLATE.md

Note: Sessions are created in the consuming repo, not in the ATDD package itself.
      This validator runs against {consumer_repo}/sessions/ directory.

Supports two formats:
1. Hybrid (new): YAML frontmatter + Markdown body
2. Legacy: Pure Markdown with **Field:** patterns

Run: python3 -m pytest src/atdd/coach/validators/test_session_validation.py -v
"""
import pytest
import re
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any
import yaml


# ============================================================================
# Configuration
# ============================================================================

# Package paths (relative to this file)
ATDD_PKG_ROOT = Path(__file__).parent.parent.parent  # src/atdd
CONVENTION_FILE = ATDD_PKG_ROOT / "coach" / "conventions" / "session.convention.yaml"
TEMPLATE_FILE = ATDD_PKG_ROOT / "coach" / "templates" / "SESSION-TEMPLATE.md"

# Consumer repo paths (where sessions are created via `atdd init`)
# Default to current working directory, can be overridden
REPO_ROOT = Path.cwd()
SESSIONS_DIR = REPO_ROOT / "atdd-sessions"

# Valid values from convention
VALID_STATUSES = {"INIT", "PLANNED", "ACTIVE", "BLOCKED", "COMPLETE", "OBSOLETE"}
VALID_TYPES = {"implementation", "migration", "refactor", "analysis", "planning", "cleanup", "tracking"}
VALID_ARCHETYPES = {"db", "be", "fe", "contracts", "wmbt", "wagon", "train", "telemetry", "migrations"}
VALID_PROGRESS_STATUSES = {"TODO", "IN_PROGRESS", "DONE", "BLOCKED", "SKIPPED", "N/A"}
VALID_COMPLEXITIES = {1, 2, 3, 4, 5}

# Required markdown sections (in body)
REQUIRED_BODY_SECTIONS = [
    "Context",
    "Architecture",
    "Phases",
    "Validation",
    "Session Log",
]

# Required frontmatter fields
REQUIRED_FRONTMATTER_FIELDS = [
    "session",
    "title",
    "date",
    "status",
    "branch",
    "type",
    "complexity",
    "archetypes",
]


# ============================================================================
# Parsing Functions
# ============================================================================

def parse_frontmatter(content: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Parse YAML frontmatter from content.

    Returns:
        Tuple of (frontmatter_dict or None, body_content)
    """
    if not content.startswith("---"):
        return None, content

    # Find the closing ---
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, content

    try:
        frontmatter = yaml.safe_load(parts[1])
        body = parts[2]
        return frontmatter, body
    except yaml.YAMLError:
        return None, content


def parse_legacy_header(content: str) -> Dict[str, str]:
    """
    Parse legacy Markdown header with **Field:** patterns.
    """
    header = {}

    patterns = {
        "title": r"^#\s+SESSION-(\d+):\s+(.+)$",
        "date": r"\*\*Date:\*\*\s*(.+)",
        "status": r"\*\*Status:\*\*\s*(\S+)",
        "branch": r"\*\*Branch:\*\*\s*(.+)",
        "type": r"\*\*Type:\*\*\s*(\w+)",
        "complexity": r"\*\*Complexity:\*\*\s*(\d)",
        "archetypes": r"\*\*Archetypes:\*\*\s*(.+)",
    }

    for field, pattern in patterns.items():
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            if field == "title":
                header["session"] = match.group(1)
                header["title"] = match.group(2).strip()
            else:
                header[field] = match.group(1).strip()

    return header


def parse_session_file(path: Path) -> Dict[str, Any]:
    """
    Parse a session file (hybrid or legacy format).

    Returns structured data with:
    - path: Path object
    - name: filename
    - format: "hybrid" or "legacy"
    - frontmatter: dict (from YAML or parsed legacy)
    - body: markdown content
    - sections: set of ## headings in body
    """
    content = path.read_text()

    result = {
        "path": path,
        "name": path.name,
        "content": content,
        "frontmatter": {},
        "body": "",
        "sections": set(),
        "format": "unknown",
    }

    # Try hybrid format first (YAML frontmatter)
    frontmatter, body = parse_frontmatter(content)

    if frontmatter:
        result["format"] = "hybrid"
        result["frontmatter"] = frontmatter
        result["body"] = body
    else:
        # Fall back to legacy format
        result["format"] = "legacy"
        result["frontmatter"] = parse_legacy_header(content)
        result["body"] = content

    # Extract sections from body
    section_pattern = r"^##\s+(.+)$"
    for match in re.finditer(section_pattern, result["body"], re.MULTILINE):
        section_name = match.group(1).strip()
        result["sections"].add(section_name)

    return result


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def convention() -> Dict:
    """Load session convention file."""
    if not CONVENTION_FILE.exists():
        pytest.skip(f"Convention file not found: {CONVENTION_FILE}")

    with open(CONVENTION_FILE) as f:
        return yaml.safe_load(f)


@pytest.fixture
def session_files() -> List[Path]:
    """Get all session files (excluding template and archive)."""
    if not SESSIONS_DIR.exists():
        pytest.skip(f"Sessions directory not found: {SESSIONS_DIR}. Run 'atdd init' first.")

    files = []
    for f in SESSIONS_DIR.glob("SESSION-*.md"):
        # Skip template
        if f.name == "SESSION-TEMPLATE.md":
            continue
        files.append(f)

    return sorted(files)


@pytest.fixture
def hybrid_session_files(session_files: List[Path]) -> List[Path]:
    """Get session files using hybrid format (YAML frontmatter)."""
    hybrid = []
    for f in session_files:
        content = f.read_text()
        if content.startswith("---"):
            hybrid.append(f)
    return hybrid


@pytest.fixture
def active_session_files(session_files: List[Path]) -> List[Path]:
    """Get only active session files (not COMPLETE or OBSOLETE)."""
    active = []
    for f in session_files:
        parsed = parse_session_file(f)
        status = str(parsed["frontmatter"].get("status", "")).upper()
        status_word = status.split()[0] if status else ""

        if status_word not in {"COMPLETE", "OBSOLETE"}:
            active.append(f)
    return active


# ============================================================================
# Hybrid Format Validation Tests
# ============================================================================

def test_hybrid_sessions_have_valid_frontmatter(hybrid_session_files: List[Path]):
    """
    Test that hybrid sessions have parseable YAML frontmatter.
    """
    invalid = []

    for f in hybrid_session_files:
        content = f.read_text()
        frontmatter, _ = parse_frontmatter(content)

        if frontmatter is None:
            invalid.append(f"{f.name}: YAML frontmatter parse error")

    if invalid:
        pytest.fail(f"Invalid YAML frontmatter:\n" + "\n".join(f"  - {i}" for i in invalid))


def test_hybrid_sessions_have_required_frontmatter_fields(hybrid_session_files: List[Path]):
    """
    Test that hybrid sessions have all required frontmatter fields.
    """
    missing = []

    for f in hybrid_session_files:
        parsed = parse_session_file(f)

        if parsed["format"] != "hybrid":
            continue

        fm = parsed["frontmatter"]
        for field in REQUIRED_FRONTMATTER_FIELDS:
            if field not in fm:
                missing.append(f"{f.name}: missing frontmatter field '{field}'")

    if missing:
        pytest.fail(f"Missing frontmatter fields:\n" + "\n".join(f"  - {m}" for m in missing))


def test_hybrid_sessions_have_valid_progress_structure(hybrid_session_files: List[Path]):
    """
    Test that hybrid sessions have valid progress structure in frontmatter.
    """
    invalid = []

    for f in hybrid_session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]

        if "progress" not in fm:
            continue

        progress = fm["progress"]

        # Check phases
        if "phases" in progress:
            for phase in progress["phases"]:
                if "id" not in phase:
                    invalid.append(f"{f.name}: phase missing 'id'")
                if "status" not in phase:
                    invalid.append(f"{f.name}: phase missing 'status'")
                elif phase["status"] not in VALID_PROGRESS_STATUSES:
                    invalid.append(f"{f.name}: phase status '{phase['status']}' invalid")

        # Check WMBT (for implementation sessions)
        if "wmbt" in progress:
            for wmbt in progress["wmbt"]:
                if "id" not in wmbt:
                    invalid.append(f"{f.name}: WMBT missing 'id'")
                for phase in ["red", "green", "refactor"]:
                    if phase in wmbt and wmbt[phase] not in VALID_PROGRESS_STATUSES:
                        invalid.append(f"{f.name}: WMBT {wmbt.get('id')} {phase} status invalid")

    if invalid:
        pytest.fail(f"Invalid progress structure:\n" + "\n".join(f"  - {i}" for i in invalid))


def test_hybrid_sessions_have_success_criteria(hybrid_session_files: List[Path]):
    """
    Test that hybrid sessions have success_criteria in frontmatter.
    """
    missing = []

    for f in hybrid_session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]

        if "success_criteria" not in fm:
            missing.append(f"{f.name}: missing success_criteria")
        elif not isinstance(fm["success_criteria"], list):
            missing.append(f"{f.name}: success_criteria must be a list")
        elif len(fm["success_criteria"]) == 0:
            missing.append(f"{f.name}: success_criteria is empty")

    if missing:
        pytest.fail(f"Missing success criteria:\n" + "\n".join(f"  - {m}" for m in missing))


# ============================================================================
# General Validation Tests (Both Formats)
# ============================================================================

def test_session_files_have_valid_naming(session_files: List[Path]):
    """
    Test that session files follow naming convention.

    Patterns:
    - SESSION-{NN}-{slug}.md (active)
    - SESSION-{NN}-{slug}-(completed).md (completed)
    - SESSION-{NN}-{slug}-✅.md (completed with checkmark)
    """
    pattern = re.compile(r"^SESSION-(\d{2})-([a-z0-9-]+)(-\(completed\)|-✅)?\.md$")

    invalid = []
    for f in session_files:
        if not pattern.match(f.name):
            invalid.append(f.name)

    if invalid:
        pytest.fail(f"Invalid session file names:\n" + "\n".join(f"  - {n}" for n in invalid))


def test_session_status_is_valid(session_files: List[Path]):
    """
    Test that session status is a valid value.

    Valid: INIT, PLANNED, ACTIVE, BLOCKED, COMPLETE, OBSOLETE
    """
    invalid = []

    # Status aliases for legacy format
    status_aliases = {
        "IN_PROGRESS": "ACTIVE",
        "IN": "ACTIVE",
    }

    for f in session_files:
        parsed = parse_session_file(f)
        status_raw = str(parsed["frontmatter"].get("status", "")).upper()
        status_word = status_raw.split()[0] if status_raw else ""

        # Apply aliases
        status = status_aliases.get(status_word, status_word)

        if status and status not in VALID_STATUSES:
            invalid.append(f"{f.name}: status '{status_raw}' not in {VALID_STATUSES}")

    if invalid:
        pytest.fail(f"Invalid status values:\n" + "\n".join(f"  - {i}" for i in invalid))


def test_session_type_is_valid(session_files: List[Path]):
    """
    Test that session type is a valid value.
    """
    invalid = []

    for f in session_files:
        parsed = parse_session_file(f)
        session_type = str(parsed["frontmatter"].get("type", "")).lower()

        if session_type and session_type not in VALID_TYPES:
            invalid.append(f"{f.name}: type '{session_type}' not in {VALID_TYPES}")

    if invalid:
        pytest.fail(f"Invalid type values:\n" + "\n".join(f"  - {i}" for i in invalid))


def test_session_archetypes_are_valid(session_files: List[Path]):
    """
    Test that session archetypes are valid values.
    """
    invalid = []

    for f in session_files:
        parsed = parse_session_file(f)
        archetypes_raw = parsed["frontmatter"].get("archetypes", [])

        # Handle both list (hybrid) and string (legacy) formats
        if isinstance(archetypes_raw, str):
            archetypes = [a.strip().lower() for a in archetypes_raw.split(",")]
        elif isinstance(archetypes_raw, list):
            archetypes = [str(a).lower() for a in archetypes_raw]
        else:
            archetypes = []

        for arch in archetypes:
            if arch and arch not in VALID_ARCHETYPES and not arch.startswith("{"):
                invalid.append(f"{f.name}: archetype '{arch}' not in {VALID_ARCHETYPES}")

    if invalid:
        pytest.fail(f"Invalid archetype values:\n" + "\n".join(f"  - {i}" for i in invalid))


def test_session_complexity_is_valid(session_files: List[Path]):
    """
    Test that session complexity is 1-5.
    """
    invalid = []

    for f in session_files:
        parsed = parse_session_file(f)
        complexity = parsed["frontmatter"].get("complexity")

        if complexity is not None:
            try:
                c = int(complexity)
                if c not in VALID_COMPLEXITIES:
                    invalid.append(f"{f.name}: complexity {c} not in 1-5")
            except (ValueError, TypeError):
                invalid.append(f"{f.name}: complexity '{complexity}' not a number")

    if invalid:
        pytest.fail(f"Invalid complexity values:\n" + "\n".join(f"  - {i}" for i in invalid))


def test_session_files_have_required_body_sections(session_files: List[Path]):
    """
    Test that all session files have required sections in body.
    """
    missing = []

    for f in session_files:
        parsed = parse_session_file(f)

        for section in REQUIRED_BODY_SECTIONS:
            if section not in parsed["sections"]:
                missing.append(f"{f.name}: missing ## {section}")

    if missing:
        pytest.fail(
            f"Missing required body sections ({len(missing)} violations):\n" +
            "\n".join(f"  - {m}" for m in missing[:20]) +
            (f"\n  ... and {len(missing) - 20} more" if len(missing) > 20 else "")
        )


def test_session_has_session_log_entry(active_session_files: List[Path]):
    """
    Test that active sessions have at least one Session Log entry.
    """
    missing = []

    for f in active_session_files:
        parsed = parse_session_file(f)
        body = parsed["body"]

        # Look for ### Session N pattern
        if not re.search(r"###\s+Session\s+\d+", body):
            missing.append(f"{f.name}: no Session Log entries (### Session N)")

    if missing:
        pytest.fail(f"Missing Session Log entries:\n" + "\n".join(f"  - {m}" for m in missing))


def test_session_has_gate_commands(active_session_files: List[Path]):
    """
    Test that active sessions have gate commands for validation.
    """
    missing = []

    for f in active_session_files:
        parsed = parse_session_file(f)
        body = parsed["body"]

        # Look for code blocks with commands
        has_gate = re.search(r"```(?:bash|shell)?\n[^`]*(?:pytest|python|npm|supabase)", body)

        if not has_gate:
            missing.append(f"{f.name}: no gate commands found")

    if missing:
        pytest.fail(f"Missing gate commands:\n" + "\n".join(f"  - {m}" for m in missing))


# ============================================================================
# Pre-Implementation Gate
# ============================================================================

def test_planned_sessions_ready_for_implementation(session_files: List[Path]):
    """
    Test that PLANNED sessions have all required elements before implementation.

    This is the main gate to run before starting implementation.

    Checks:
    1. Status is PLANNED (not INIT)
    2. All required sections present
    3. Scope is defined
    4. Phases are defined
    5. Success criteria are defined
    6. Gate commands are present
    """
    issues = []

    for f in session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]
        status = str(fm.get("status", "")).upper().split()[0] if fm.get("status") else ""

        # Only check PLANNED sessions
        if status != "PLANNED":
            continue

        session_issues = []
        body = parsed["body"]

        # Check required body sections
        for section in REQUIRED_BODY_SECTIONS:
            if section not in parsed["sections"]:
                session_issues.append(f"missing body section: {section}")

        # Check scope definition (frontmatter or body)
        has_scope = False
        if "scope" in fm and fm["scope"]:
            has_scope = True
        elif "In Scope" in body or "In scope" in body:
            has_scope = True

        if not has_scope:
            session_issues.append("missing scope definition")

        # Check phases defined (frontmatter or body)
        has_phases = False
        if "progress" in fm and "phases" in fm.get("progress", {}):
            has_phases = True
        elif re.search(r"###\s+Phase\s+\d+", body):
            has_phases = True

        if not has_phases:
            session_issues.append("no phases defined")

        # Check success criteria (frontmatter or body)
        has_criteria = False
        if "success_criteria" in fm and fm["success_criteria"]:
            has_criteria = True
        elif re.search(r"- \[[ x]\]", body):
            has_criteria = True

        if not has_criteria:
            session_issues.append("no success criteria")

        # Check gate commands
        if not re.search(r"```(?:bash|shell)?\n[^`]*(?:pytest|python|npm)", body):
            session_issues.append("no gate commands")

        if session_issues:
            issues.append(f"{f.name}:\n" + "\n".join(f"    - {i}" for i in session_issues))

    if issues:
        pytest.fail(
            f"PLANNED sessions not ready for implementation:\n\n" +
            "\n\n".join(issues)
        )


# ============================================================================
# Implementation Session Tests
# ============================================================================

def test_implementation_sessions_have_wmbt_tracking(session_files: List[Path]):
    """
    Test that implementation sessions have WMBT tracking.

    Checks frontmatter progress.wmbt or body WMBT Status section.
    """
    missing = []

    for f in session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]
        session_type = str(fm.get("type", "")).lower()

        if session_type != "implementation":
            continue

        # Check frontmatter
        has_wmbt_frontmatter = (
            "progress" in fm and
            "wmbt" in fm.get("progress", {}) and
            len(fm["progress"]["wmbt"]) > 0
        )

        # Check body
        has_wmbt_body = "WMBT Status" in parsed["body"] or "WMBT" in parsed["sections"]

        if not has_wmbt_frontmatter and not has_wmbt_body:
            missing.append(f"{f.name}: implementation session missing WMBT tracking")

    if missing:
        pytest.fail(f"Missing WMBT tracking:\n" + "\n".join(f"  - {m}" for m in missing))


def test_implementation_sessions_have_atdd_phases(session_files: List[Path]):
    """
    Test that implementation sessions track RED/GREEN/REFACTOR phases.
    """
    missing = []

    for f in session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]
        session_type = str(fm.get("type", "")).lower()

        if session_type != "implementation":
            continue

        body = parsed["body"]

        # Check frontmatter
        has_atdd_frontmatter = (
            "progress" in fm and
            "atdd" in fm.get("progress", {})
        )

        # Check body
        has_red = "RED" in body
        has_green = "GREEN" in body
        has_refactor = "REFACTOR" in body
        has_atdd_body = has_red and has_green and has_refactor

        if not has_atdd_frontmatter and not has_atdd_body:
            missing_phases = []
            if not has_red:
                missing_phases.append("RED")
            if not has_green:
                missing_phases.append("GREEN")
            if not has_refactor:
                missing_phases.append("REFACTOR")
            missing.append(f"{f.name}: missing ATDD phases: {', '.join(missing_phases)}")

    if missing:
        pytest.fail(f"Missing ATDD phases:\n" + "\n".join(f"  - {m}" for m in missing))


# ============================================================================
# Gate Tests Validation
# ============================================================================

# Required ATDD validators per archetype (from session.convention.yaml)
REQUIRED_VALIDATORS_BY_ARCHETYPE = {
    "db": [
        "atdd/tester/validators/test_migration_coverage.py",
    ],
    "be": [
        "atdd/coder/validators/test_python_architecture.py",
        "atdd/coder/validators/test_import_boundaries.py",
    ],
    "fe": [
        "atdd/coder/validators/test_typescript_architecture.py",
    ],
    "contracts": [
        "atdd/tester/validators/test_contract_schema_compliance.py",
    ],
    "wmbt": [
        "atdd/planner/validators/test_wmbt_consistency.py",
    ],
    "wagon": [
        "atdd/planner/validators/test_wagon_urn_chain.py",
        "atdd/coder/validators/test_wagon_boundaries.py",
    ],
    "train": [
        "atdd/planner/validators/test_train_validation.py",
    ],
    "telemetry": [
        "atdd/tester/validators/test_telemetry_structure.py",
    ],
    "migrations": [
        "atdd/tester/validators/test_migration_coverage.py",
    ],
}

# Universal required validators (all sessions)
UNIVERSAL_VALIDATORS = [
    "atdd/coach/validators/test_session_validation.py",
]

# Valid gate test phases
VALID_GATE_PHASES = {"design", "implementation", "validation", "completion"}

# Valid gate test expected values
VALID_GATE_EXPECTED = {"PASS", "FAIL"}


def test_hybrid_sessions_have_gate_tests(hybrid_session_files: List[Path]):
    """
    Test that hybrid sessions have gate_tests defined in frontmatter.

    Gate tests are required to enforce conventions via ATDD validators.
    """
    missing = []

    for f in hybrid_session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]

        if "gate_tests" not in fm:
            missing.append(f"{f.name}: missing gate_tests in frontmatter")
        elif not isinstance(fm["gate_tests"], list):
            missing.append(f"{f.name}: gate_tests must be a list")
        elif len(fm["gate_tests"]) == 0:
            missing.append(f"{f.name}: gate_tests is empty")

    if missing:
        pytest.fail(f"Missing gate_tests:\n" + "\n".join(f"  - {m}" for m in missing))


def test_gate_tests_have_valid_structure(hybrid_session_files: List[Path]):
    """
    Test that gate_tests have valid structure with required fields.

    Required fields: id, phase, archetype, command, expected, atdd_validator, status
    """
    invalid = []

    required_fields = ["id", "phase", "archetype", "command", "expected", "atdd_validator"]

    for f in hybrid_session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]

        if "gate_tests" not in fm or not isinstance(fm["gate_tests"], list):
            continue

        for idx, gate in enumerate(fm["gate_tests"]):
            if not isinstance(gate, dict):
                invalid.append(f"{f.name}: gate_tests[{idx}] is not a dict")
                continue

            for field in required_fields:
                if field not in gate:
                    invalid.append(f"{f.name}: gate_tests[{idx}] missing '{field}'")

            # Validate phase value
            if "phase" in gate and gate["phase"] not in VALID_GATE_PHASES:
                invalid.append(f"{f.name}: gate_tests[{idx}] phase '{gate['phase']}' invalid")

            # Validate expected value
            if "expected" in gate and gate["expected"] not in VALID_GATE_EXPECTED:
                invalid.append(f"{f.name}: gate_tests[{idx}] expected '{gate['expected']}' invalid")

            # Validate archetype value
            if "archetype" in gate:
                arch = gate["archetype"]
                if arch != "all" and arch not in VALID_ARCHETYPES and not arch.startswith("{"):
                    invalid.append(f"{f.name}: gate_tests[{idx}] archetype '{arch}' invalid")

    if invalid:
        pytest.fail(f"Invalid gate_tests structure:\n" + "\n".join(f"  - {i}" for i in invalid[:30]))


def test_gate_tests_reference_valid_atdd_validators(hybrid_session_files: List[Path]):
    """
    Test that gate_tests reference valid ATDD validator paths.

    Validator paths must:
    - Start with 'atdd/' or be 'manual' or 'feature-specific'
    - End with '.py' or be a directory path ending with '/'
    """
    invalid = []

    for f in hybrid_session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]

        if "gate_tests" not in fm or not isinstance(fm["gate_tests"], list):
            continue

        for idx, gate in enumerate(fm["gate_tests"]):
            if not isinstance(gate, dict):
                continue

            validator = gate.get("atdd_validator", "")

            # Skip special values
            if validator in ["manual", "feature-specific"]:
                continue

            # Skip template placeholders
            if validator.startswith("{"):
                continue

            # Must start with atdd/
            if not validator.startswith("atdd/"):
                invalid.append(f"{f.name}: gate_tests[{idx}] atdd_validator must start with 'atdd/'")
                continue

            # Must end with .py or /
            if not (validator.endswith(".py") or validator.endswith("/")):
                invalid.append(f"{f.name}: gate_tests[{idx}] atdd_validator must end with '.py' or '/'")

    if invalid:
        pytest.fail(f"Invalid ATDD validator references:\n" + "\n".join(f"  - {i}" for i in invalid[:30]))


def test_gate_tests_cover_declared_archetypes(hybrid_session_files: List[Path]):
    """
    Test that gate_tests exist for all declared archetypes.

    Each archetype declared in session.archetypes must have at least one
    corresponding gate_test with matching archetype or archetype='all'.
    """
    missing = []

    for f in hybrid_session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]

        # Get declared archetypes
        archetypes_raw = fm.get("archetypes", [])
        if isinstance(archetypes_raw, str):
            archetypes = [a.strip().lower() for a in archetypes_raw.split(",")]
        elif isinstance(archetypes_raw, list):
            archetypes = [str(a).lower() for a in archetypes_raw]
        else:
            continue

        # Skip template placeholders
        archetypes = [a for a in archetypes if not a.startswith("{")]

        if not archetypes:
            continue

        # Get gate_tests archetypes
        gate_tests = fm.get("gate_tests", [])
        if not isinstance(gate_tests, list):
            continue

        gate_archetypes = set()
        has_all_archetype = False

        for gate in gate_tests:
            if isinstance(gate, dict):
                arch = gate.get("archetype", "")
                if arch == "all":
                    has_all_archetype = True
                gate_archetypes.add(arch)

        # Each declared archetype needs coverage (unless 'all' is present)
        for arch in archetypes:
            if arch not in gate_archetypes and not has_all_archetype:
                missing.append(f"{f.name}: archetype '{arch}' has no gate_test")

    if missing:
        pytest.fail(f"Archetypes without gate_tests:\n" + "\n".join(f"  - {m}" for m in missing[:30]))


def test_planned_sessions_have_universal_gate_tests(session_files: List[Path]):
    """
    Test that PLANNED/ACTIVE sessions have required universal gate tests.

    Universal gates:
    - GT-001: Session validation (design phase)
    - GT-900: Full ATDD suite (completion phase)
    """
    missing = []

    for f in session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]
        status = str(fm.get("status", "")).upper().split()[0] if fm.get("status") else ""

        # Only check PLANNED and ACTIVE sessions
        if status not in {"PLANNED", "ACTIVE"}:
            continue

        # For hybrid format only
        if parsed["format"] != "hybrid":
            continue

        gate_tests = fm.get("gate_tests", [])
        if not isinstance(gate_tests, list):
            missing.append(f"{f.name}: gate_tests is not a list")
            continue

        # Extract gate IDs
        gate_ids = set()
        for gate in gate_tests:
            if isinstance(gate, dict) and "id" in gate:
                gate_ids.add(gate["id"])

        # Check for universal gates (or any design/completion gates)
        has_design_gate = any(
            isinstance(g, dict) and g.get("phase") == "design"
            for g in gate_tests
        )
        has_completion_gate = any(
            isinstance(g, dict) and g.get("phase") == "completion"
            for g in gate_tests
        )

        if not has_design_gate:
            missing.append(f"{f.name}: missing design phase gate_test")
        if not has_completion_gate:
            missing.append(f"{f.name}: missing completion phase gate_test")

    if missing:
        pytest.fail(f"Missing universal gate_tests:\n" + "\n".join(f"  - {m}" for m in missing))


# ============================================================================
# ATDD Workflow Sequence Validation
# ============================================================================

# Valid workflow phase statuses
VALID_WORKFLOW_STATUSES = {"TODO", "IN_PROGRESS", "DONE", "SKIPPED", "N/A"}

# Workflow phases and their dependencies
WORKFLOW_PHASES = {
    "planner": {"order": 1, "depends_on": []},
    "tester": {"order": 2, "depends_on": ["planner"]},
    "coder": {"order": 3, "depends_on": ["planner", "tester"]},
}

# Required workflow phases by session type
REQUIRED_WORKFLOW_PHASES_BY_TYPE = {
    "implementation": ["planner", "tester", "coder"],
    "migration": ["planner", "tester", "coder"],
    "refactor": ["tester", "coder"],
    "analysis": [],
    "planning": ["planner"],
    "cleanup": ["coder"],
    "tracking": [],
}


def test_implementation_sessions_have_workflow_phases(hybrid_session_files: List[Path]):
    """
    Test that implementation sessions have workflow_phases tracking.

    ATDD workflow: Planner → Tester → Coder
    This ensures the Plan → Test → Code sequence is followed.
    """
    missing = []

    for f in hybrid_session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]
        session_type = str(fm.get("type", "")).lower()

        # Only check implementation sessions
        if session_type != "implementation":
            continue

        if "workflow_phases" not in fm:
            missing.append(f"{f.name}: missing workflow_phases in frontmatter")
            continue

        wf = fm["workflow_phases"]

        # Check all required phases exist
        for phase in ["planner", "tester", "coder"]:
            if phase not in wf:
                missing.append(f"{f.name}: workflow_phases missing '{phase}' phase")

    if missing:
        pytest.fail(f"Missing workflow_phases:\n" + "\n".join(f"  - {m}" for m in missing))


def test_workflow_phases_have_valid_structure(hybrid_session_files: List[Path]):
    """
    Test that workflow_phases have valid structure with required fields.

    Each phase must have: status, gate, gate_status
    """
    invalid = []

    required_fields = ["status", "gate", "gate_status"]

    for f in hybrid_session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]

        if "workflow_phases" not in fm or not isinstance(fm["workflow_phases"], dict):
            continue

        wf = fm["workflow_phases"]

        for phase_name, phase_data in wf.items():
            if not isinstance(phase_data, dict):
                invalid.append(f"{f.name}: workflow_phases.{phase_name} is not a dict")
                continue

            # Validate required fields
            for field in required_fields:
                if field not in phase_data:
                    invalid.append(f"{f.name}: workflow_phases.{phase_name} missing '{field}'")

            # Validate status value
            if "status" in phase_data and phase_data["status"] not in VALID_WORKFLOW_STATUSES:
                invalid.append(f"{f.name}: workflow_phases.{phase_name}.status '{phase_data['status']}' invalid")

            # Validate gate_status value
            if "gate_status" in phase_data and phase_data["gate_status"] not in VALID_WORKFLOW_STATUSES:
                invalid.append(f"{f.name}: workflow_phases.{phase_name}.gate_status '{phase_data['gate_status']}' invalid")

    if invalid:
        pytest.fail(f"Invalid workflow_phases structure:\n" + "\n".join(f"  - {i}" for i in invalid[:30]))


def test_workflow_phase_dependencies_respected(hybrid_session_files: List[Path]):
    """
    Test that workflow phase dependencies are respected.

    ATDD workflow rules (from session.convention.yaml):
    - WF-001: MUST complete planner phase before tester phase
    - WF-002: MUST complete tester phase before coder phase
    - WF-003: MUST have RED test before writing implementation

    A phase can only be IN_PROGRESS or DONE if its dependencies are DONE or SKIPPED.
    """
    violations = []

    for f in hybrid_session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]

        if "workflow_phases" not in fm or not isinstance(fm["workflow_phases"], dict):
            continue

        wf = fm["workflow_phases"]

        for phase_name, phase_info in WORKFLOW_PHASES.items():
            if phase_name not in wf:
                continue

            phase_data = wf[phase_name]
            if not isinstance(phase_data, dict):
                continue

            phase_status = phase_data.get("status", "TODO")

            # Skip if phase is TODO, SKIPPED, or N/A
            if phase_status in {"TODO", "SKIPPED", "N/A"}:
                continue

            # If phase is IN_PROGRESS or DONE, check dependencies
            for dep in phase_info["depends_on"]:
                if dep not in wf:
                    violations.append(
                        f"{f.name}: {phase_name} is {phase_status} but dependency '{dep}' is missing"
                    )
                    continue

                dep_data = wf[dep]
                if not isinstance(dep_data, dict):
                    continue

                dep_status = dep_data.get("status", "TODO")

                # Dependency must be DONE or SKIPPED for phase to progress
                if dep_status not in {"DONE", "SKIPPED"}:
                    violations.append(
                        f"{f.name}: {phase_name} is {phase_status} but dependency '{dep}' is {dep_status} "
                        f"(violates WF-00{phase_info['order']})"
                    )

    if violations:
        pytest.fail(
            f"Workflow phase dependency violations (Plan → Test → Code):\n" +
            "\n".join(f"  - {v}" for v in violations[:20])
        )


def test_session_type_has_required_workflow_phases(hybrid_session_files: List[Path]):
    """
    Test that sessions have required workflow phases based on their type.

    Session type workflow mapping:
    - implementation: planner, tester, coder
    - migration: planner, tester, coder
    - refactor: tester, coder
    - planning: planner
    - cleanup: coder
    - analysis, tracking: none required
    """
    missing = []

    for f in hybrid_session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]
        session_type = str(fm.get("type", "")).lower()

        if session_type not in REQUIRED_WORKFLOW_PHASES_BY_TYPE:
            continue

        required_phases = REQUIRED_WORKFLOW_PHASES_BY_TYPE[session_type]
        if not required_phases:
            continue

        wf = fm.get("workflow_phases", {})
        if not isinstance(wf, dict):
            if required_phases:
                missing.append(f"{f.name}: type '{session_type}' requires workflow_phases")
            continue

        for phase in required_phases:
            if phase not in wf:
                missing.append(f"{f.name}: type '{session_type}' requires workflow_phases.{phase}")

    if missing:
        pytest.fail(
            f"Sessions missing required workflow phases for their type:\n" +
            "\n".join(f"  - {m}" for m in missing[:30])
        )


# ============================================================================
# Summary Test
# ============================================================================

def test_session_validation_summary(session_files: List[Path]):
    """
    Generate a summary of all session files and their validation status.

    This test always passes but prints a summary.
    """
    print("\n" + "=" * 70)
    print("SESSION VALIDATION SUMMARY")
    print("=" * 70)

    stats = {
        "total": len(session_files),
        "by_format": {"hybrid": 0, "legacy": 0},
        "by_status": {},
        "by_type": {},
    }

    for f in session_files:
        parsed = parse_session_file(f)
        fm = parsed["frontmatter"]

        # Format
        stats["by_format"][parsed["format"]] += 1

        # Status
        status = str(fm.get("status", "UNKNOWN")).upper().split()[0]
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

        # Type
        session_type = str(fm.get("type", "unknown")).lower()
        stats["by_type"][session_type] = stats["by_type"].get(session_type, 0) + 1

    print(f"\nTotal sessions: {stats['total']}")

    print("\nBy Format:")
    for fmt, count in stats["by_format"].items():
        print(f"  {fmt}: {count}")

    print("\nBy Status:")
    for status, count in sorted(stats["by_status"].items()):
        print(f"  {status}: {count}")

    print("\nBy Type:")
    for t, count in sorted(stats["by_type"].items()):
        print(f"  {t}: {count}")

    print("\n" + "=" * 70)
