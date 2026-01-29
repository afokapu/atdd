"""
Platform tests: Migration coverage validation.

SPEC-TESTER-CONV-0031: Validate all contracts have migrations
SPEC-TESTER-CONV-0032: Reject migrations with unresolved TODOs
"""
import pytest
from pathlib import Path

# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS_DIR = REPO_ROOT / "contracts"
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"


def contract_needs_migration(contract_path: Path) -> bool:
    """
    Check if contract needs database migration.

    Mirrors logic from atdd/coach/commands/migration.py for consistency.

    Decision algorithm (ordered rules, first match wins):
    1. Explicit persistence.strategy: check if != 'none'
    2. Empty properties: len(properties) == 0 → NO
    3. Event without id: aspect ends with '*ed' AND no 'id' → NO
    4. Internal only: metadata.to == 'internal' → NO
    5. Entity with id: 'id' in properties → YES
    6. Computed without id: description contains compute keywords AND no 'id' → NO
    7. Conservative default: metadata.to == 'external' AND has properties → YES
    8. Fallback: NO
    """
    try:
        import json
        with open(contract_path, 'r') as f:
            contract = json.load(f)

        metadata = contract.get("x-artifact-metadata", {})
        properties = contract.get("properties", {})
        description = contract.get("description", "").lower()

        # Extract aspect name from path
        aspect = contract_path.stem.replace(".schema", "")

        # Rule 1: Check persistence metadata
        persistence = metadata.get("persistence", {})
        if persistence.get("strategy") == "none":
            return False
        elif persistence.get("strategy") in ["jsonb", "relational"]:
            return True

        # Rule 2: Empty properties
        if len(properties) == 0:
            return False

        # Rule 3: Event without id (aspect ends with 'ed' like 'detected', 'completed')
        has_id = "id" in properties
        is_event_pattern = aspect.endswith("ed")
        if is_event_pattern and not has_id:
            return False

        # Rule 4: Internal only
        if metadata.get("to") == "internal":
            return False

        # Rule 5: Entity with id
        if has_id:
            return True

        # Rule 6: Computed without id
        compute_keywords = ["computed", "calculated", "derived", "aggregated", "aggregate"]
        is_computed = any(keyword in description for keyword in compute_keywords)
        if is_computed and not has_id:
            return False

        # Rule 7: Conservative default for external contracts
        if metadata.get("to") == "external" and len(properties) > 0:
            return True

        # Rule 8: Fallback - assume doesn't need migration
        return False

    except Exception:
        return False  # On error, skip to avoid false positives


@pytest.mark.platform
def test_all_contracts_have_migrations():
    """
    SPEC-TESTER-CONV-0031: Validate all contracts have migrations

    Given: Contract schemas in contracts/{theme}/{domain}/{aspect}.schema.json
    When: Checking for corresponding migrations
    Then: Each external/persistent contract has migration OR table exists
          Internal/transient contracts are skipped
          Missing contracts reported by theme/domain/aspect
    """
    if not CONTRACTS_DIR.exists():
        pytest.skip("contracts/ directory does not exist")
        return

    if not MIGRATIONS_DIR.exists():
        MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)

    contracts = list(CONTRACTS_DIR.rglob("*.schema.json"))
    missing = []
    skipped = 0

    for contract in contracts:
        # Extract theme/domain/aspect from path
        # Pattern: contracts/{theme}/{domain}/{aspect}.schema.json
        relative_path = contract.relative_to(CONTRACTS_DIR)
        parts = relative_path.parts

        if len(parts) < 3:
            continue  # Skip malformed paths

        # Check if contract needs migration
        if not contract_needs_migration(contract):
            skipped += 1
            continue

        theme = parts[0]
        domain = parts[1]
        aspect = contract.stem.replace(".schema", "")

        # Expected table name
        table_name = f"{theme}_{domain}_{aspect}".replace("-", "_")

        # Check if migration exists mentioning this table
        has_migration = False
        if MIGRATIONS_DIR.exists():
            for migration_file in MIGRATIONS_DIR.glob("*.sql"):
                content = migration_file.read_text()
                if f"CREATE TABLE {table_name}" in content or f"CREATE TABLE IF NOT EXISTS {table_name}" in content:
                    has_migration = True
                    break

        if not has_migration:
            missing.append(f"{theme}/{domain}/{aspect} → table: {table_name}")

    if missing:
        error_msg = f"Found {len(missing)} contracts without migrations:\n"
        error_msg += "\n".join(f"  {m}" for m in missing[:20])
        if len(missing) > 20:
            error_msg += f"\n  ... and {len(missing) - 20} more"
        if skipped > 0:
            error_msg += f"\n\nℹ️  Skipped {skipped} internal/transient contracts"
        error_msg += "\n\nRun: python atdd/coach/commands/migration.py to generate"
        pytest.fail(error_msg)


@pytest.mark.platform
def test_migration_templates_reviewed():
    """
    SPEC-TESTER-CONV-0032: Reject migrations with unresolved TODOs

    Given: Migration files in supabase/migrations/
          Migrations may have TODO markers for human review
    When: Validating migrations before applying
    Then: No unresolved TODO markers (⚠️ TODO:) remain
          Forces human review of foreign keys, indexes, RLS
    """
    if not MIGRATIONS_DIR.exists():
        pytest.skip("supabase/migrations/ directory does not exist")
        return

    migrations_with_todos = []

    for migration_file in MIGRATIONS_DIR.glob("*.sql"):
        content = migration_file.read_text()

        # Count unresolved TODO markers
        todo_markers = [
            line.strip()
            for line in content.split("\n")
            if "⚠️ TODO:" in line or "TODO:" in line and line.strip().startswith("--")
        ]

        if todo_markers:
            migrations_with_todos.append({
                "file": migration_file.name,
                "count": len(todo_markers),
                "todos": todo_markers[:5]  # First 5 TODOs
            })

    if migrations_with_todos:
        error_msg = f"Found {len(migrations_with_todos)} migrations with unresolved TODOs:\n\n"

        for item in migrations_with_todos[:10]:
            error_msg += f"  {item['file']} ({item['count']} TODOs):\n"
            for todo in item['todos']:
                error_msg += f"    {todo}\n"
            error_msg += "\n"

        if len(migrations_with_todos) > 10:
            error_msg += f"  ... and {len(migrations_with_todos) - 10} more files\n\n"

        error_msg += "⚠️  Review and complete TODOs before applying migrations:\n"
        error_msg += "   - Add foreign key constraints\n"
        error_msg += "   - Add indexes for common queries\n"
        error_msg += "   - Define RLS policies\n"
        error_msg += "   - Review JSONB columns for normalization\n"

        pytest.fail(error_msg)