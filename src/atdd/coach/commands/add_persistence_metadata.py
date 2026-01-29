#!/usr/bin/env python3
"""
Add persistence metadata to contracts based on existing migrations.

Links contracts to database tables for bidirectional traceability.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS_DIR = REPO_ROOT / "contracts"
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"


def find_migration_for_table(table_name: str) -> Optional[str]:
    """Find migration file that created a specific table."""
    for migration_file in MIGRATIONS_DIR.glob("*.sql"):
        content = migration_file.read_text()
        if f"CREATE TABLE IF NOT EXISTS {table_name}" in content or \
           f"CREATE TABLE {table_name}" in content:
            return f"supabase/migrations/{migration_file.name}"
    return None


def extract_indexes_from_migration(migration_path: Path, table_name: str) -> List[Dict]:
    """Extract index definitions from migration file."""
    indexes = []
    content = migration_path.read_text()

    # Match: CREATE INDEX idx_name ON table_name ...
    index_pattern = rf"CREATE INDEX (\w+) ON {table_name}(?: USING (\w+))?\s*\((.*?)\)"

    for match in re.finditer(index_pattern, content, re.MULTILINE):
        index_name = match.group(1)
        index_type = match.group(2).lower() if match.group(2) else "btree"
        fields_raw = match.group(3)

        # Parse fields (handle JSONB -> notation)
        fields = [f.strip() for f in fields_raw.split(",")]

        indexes.append({
            "name": index_name,
            "type": index_type,
            "fields": fields
        })

    return indexes


def add_persistence_to_contract(contract_path: Path, table_name: str, migration_path: str, indexes: List[Dict]) -> bool:
    """Add persistence metadata to a contract file."""
    try:
        with open(contract_path) as f:
            contract = json.load(f)

        metadata = contract.get("x-artifact-metadata", {})

        # Check if already has persistence
        if "persistence" in metadata:
            print(f"  ⚠️  {contract_path.name} already has persistence metadata")
            return False

        # Add persistence metadata
        metadata["persistence"] = {
            "strategy": "jsonb",
            "table": table_name,
            "migration": migration_path,
            "indexes": indexes
        }

        contract["x-artifact-metadata"] = metadata

        # Write back with pretty formatting
        with open(contract_path, 'w') as f:
            json.dump(contract, f, indent=2)
            f.write('\n')  # Add trailing newline

        return True

    except Exception as e:
        print(f"  ❌ Error updating {contract_path.name}: {e}")
        return False


def contract_id_to_path(contract_id: str) -> Optional[Path]:
    """Convert contract $id to file path.

    Examples:
        commons:ux:themes:skin → contracts/commons/ux/themes/skin.schema.json
        match:dilemma:current → contracts/match/dilemma/current.schema.json
    """
    parts = contract_id.split(":")
    if len(parts) < 2:
        return None

    # Build path: contracts/{theme}/{path...}/{aspect}.schema.json
    path = CONTRACTS_DIR / "/".join(parts[:-1]) / f"{parts[-1]}.schema.json"

    return path if path.exists() else None


def table_name_to_contract_id(table_name: str) -> str:
    """Convert table name back to contract $id.

    Examples:
        commons_ux_skin → commons:ux:themes:skin (if that contract exists)
        match_dilemma_current → match:dilemma:current
    """
    # Try different path depths
    parts = table_name.split("_")

    # Try as-is first: match_dilemma_current → match:dilemma:current
    contract_id = ":".join(parts)
    path = contract_id_to_path(contract_id)
    if path:
        return contract_id

    # For commons_ux_skin, we need to find the actual contract
    # Check if it's a nested structure by trying different combinations
    for i in range(1, len(parts)):
        theme = parts[0]
        mid_parts = parts[1:i+1]
        aspect = parts[i+1] if i+1 < len(parts) else parts[-1]

        # Try: theme:mid1:mid2:...:aspect
        test_id = f"{theme}:{':'.join(mid_parts)}:{aspect}"
        path = contract_id_to_path(test_id)
        if path:
            return test_id

    # Fallback to simple conversion
    return ":".join(parts)


def main():
    """Add persistence metadata to all contracts with existing migrations."""
    print("=" * 80)
    print("Add Persistence Metadata to Contracts")
    print("=" * 80)
    print()

    # Find all tables in migrations
    tables_found = {}

    for migration_file in MIGRATIONS_DIR.glob("*.sql"):
        content = migration_file.read_text()

        # Find all CREATE TABLE statements
        pattern = r"CREATE TABLE IF NOT EXISTS (\w+)|CREATE TABLE (\w+)"
        for match in re.finditer(pattern, content):
            table_name = match.group(1) or match.group(2)
            if table_name and table_name not in ["information_schema", "pg_catalog"]:
                tables_found[table_name] = migration_file

    print(f"Found {len(tables_found)} tables in migrations:\n")

    updated = 0
    skipped = 0
    errors = 0

    for table_name, migration_file in tables_found.items():
        print(f"📋 Processing table: {table_name}")

        # Convert table name to contract ID
        contract_id = table_name_to_contract_id(table_name)
        contract_path = contract_id_to_path(contract_id)

        if not contract_path:
            print(f"  ⚠️  No contract found for table {table_name}")
            errors += 1
            continue

        print(f"  Contract: {contract_path.relative_to(REPO_ROOT)}")

        # Get migration path
        migration_rel_path = f"supabase/migrations/{migration_file.name}"

        # Extract indexes
        indexes = extract_indexes_from_migration(migration_file, table_name)
        print(f"  Indexes: {len(indexes)}")

        # Add persistence metadata
        if add_persistence_to_contract(contract_path, table_name, migration_rel_path, indexes):
            print(f"  ✅ Added persistence metadata")
            updated += 1
        else:
            skipped += 1

        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Tables found: {len(tables_found)}")
    print(f"  ✅ Updated: {updated}")
    print(f"  ⏭️  Skipped: {skipped}")
    print(f"  ❌ Errors: {errors}")
    print()

    if updated > 0:
        print("✅ Persistence metadata added to contracts!")
        print("   Contracts now link to their database tables.")
        print()
        print("Next steps:")
        print("  1. Review the updated contracts")
        print("  2. Commit the changes")
        print("  3. Run validation: pytest tests/platform_validation/")


if __name__ == "__main__":
    main()
