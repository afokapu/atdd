#!/usr/bin/env python3
"""
Analyze which migrations should be kept vs deleted based on refined criteria.

Shows a clear diff before any deletion happens.
"""

import json
from pathlib import Path
from collections import defaultdict

# Import the refined criteria function
from migration import contract_needs_migration, REPO_ROOT, CONTRACTS_DIR, MIGRATIONS_DIR


def analyze_migration_status():
    """Analyze all contracts and migrations, show what should be kept/deleted."""

    print("=" * 80)
    print("MIGRATION ANALYSIS - Refined Criteria")
    print("=" * 80)
    print()

    # Scan all contracts
    contracts = list(CONTRACTS_DIR.rglob("*.schema.json"))

    keep_migrations = []
    delete_migrations = []
    missing_migrations = []

    for contract in contracts:
        relative_path = contract.relative_to(CONTRACTS_DIR)
        parts = relative_path.parts

        if len(parts) < 3:
            continue

        theme = parts[0]
        domain = parts[1]
        aspect = contract.stem.replace(".schema", "")
        table_name = f"{theme}_{domain}_{aspect}".replace("-", "_")

        # Check if contract needs migration
        needs_migration = contract_needs_migration(contract)

        # Find existing migration
        existing_migration = None
        for mig in MIGRATIONS_DIR.glob("*.sql"):
            if f"CREATE TABLE {table_name}" in mig.read_text() or \
               f"CREATE TABLE IF NOT EXISTS {table_name}" in mig.read_text():
                existing_migration = mig
                break

        # Categorize
        if needs_migration:
            if existing_migration:
                keep_migrations.append({
                    "contract": relative_path,
                    "migration": existing_migration.name,
                    "table": table_name,
                    "reason": _get_reason(contract)
                })
            else:
                missing_migrations.append({
                    "contract": relative_path,
                    "table": table_name,
                    "reason": _get_reason(contract)
                })
        else:
            if existing_migration:
                delete_migrations.append({
                    "contract": relative_path,
                    "migration": existing_migration.name,
                    "table": table_name,
                    "reason": _get_exclusion_reason(contract)
                })

    # Print summary
    print(f"📊 SUMMARY")
    print(f"  Total contracts: {len(contracts)}")
    print(f"  ✅ Keep migrations: {len(keep_migrations)}")
    print(f"  ❌ Delete migrations: {len(delete_migrations)}")
    print(f"  ⚠️  Missing migrations: {len(missing_migrations)}")
    print()

    # Show migrations to KEEP
    print("=" * 80)
    print("✅ MIGRATIONS TO KEEP")
    print("=" * 80)
    for item in keep_migrations:
        print(f"\n  📄 {item['migration']}")
        print(f"     Contract: {item['contract']}")
        print(f"     Table: {item['table']}")
        print(f"     Reason: {item['reason']}")

    # Show migrations to DELETE
    print()
    print("=" * 80)
    print("❌ MIGRATIONS TO DELETE")
    print("=" * 80)
    for item in delete_migrations:
        print(f"\n  🗑️  {item['migration']}")
        print(f"     Contract: {item['contract']}")
        print(f"     Table: {item['table']}")
        print(f"     Reason: {item['reason']}")

    # Show missing migrations
    if missing_migrations:
        print()
        print("=" * 80)
        print("⚠️  MISSING MIGRATIONS (need to generate)")
        print("=" * 80)
        for item in missing_migrations:
            print(f"\n  ⚠️  {item['table']}")
            print(f"     Contract: {item['contract']}")
            print(f"     Reason: {item['reason']}")

    print()
    print("=" * 80)
    print()

    return keep_migrations, delete_migrations, missing_migrations


def _get_reason(contract_path: Path) -> str:
    """Get the reason why a contract needs migration."""
    with open(contract_path) as f:
        contract = json.load(f)

    metadata = contract.get("x-artifact-metadata", {})
    properties = contract.get("properties", {})
    aspect = contract_path.stem.replace(".schema", "")

    if "persistent" in metadata and metadata["persistent"]:
        return "Explicit persistent: true"

    if "id" in properties:
        if aspect.endswith("ed"):
            return "Has id field (overrides event pattern)"
        return "Has id field (entity)"

    if metadata.get("to") == "external" and len(properties) > 0:
        return "Conservative default (external + properties)"

    return "Unknown"


def _get_exclusion_reason(contract_path: Path) -> str:
    """Get the reason why a contract doesn't need migration."""
    with open(contract_path) as f:
        contract = json.load(f)

    metadata = contract.get("x-artifact-metadata", {})
    properties = contract.get("properties", {})
    description = contract.get("description", "").lower()
    aspect = contract_path.stem.replace(".schema", "")

    if "persistent" in metadata and not metadata["persistent"]:
        return "Explicit persistent: false"

    if len(properties) == 0:
        return "Empty contract (pure signal)"

    has_id = "id" in properties
    is_event_pattern = aspect.endswith("ed")

    if is_event_pattern and not has_id:
        return "Event pattern without id"

    if metadata.get("to") == "internal":
        return "Internal contract (transient DTO)"

    compute_keywords = ["computed", "calculated", "derived", "aggregated", "aggregate"]
    is_computed = any(keyword in description for keyword in compute_keywords)
    if is_computed and not has_id:
        return "Computed value without id"

    return "Fallback (no migration needed)"


if __name__ == "__main__":
    keep, delete, missing = analyze_migration_status()

    print(f"\n📝 Next steps:")
    print(f"   1. Review the analysis above")
    print(f"   2. Confirm deletion of {len(delete)} migrations")
    print(f"   3. Generate {len(missing)} missing migrations")
    print()