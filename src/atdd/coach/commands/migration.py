#!/usr/bin/env python3
"""
Generate Supabase JSONB migrations from contract schemas.

SPEC-COACH-CONV-0033: Simplified JSONB-only migration generator

Usage:
    python atdd/coach/commands/migration.py                     # Generate all missing
    python atdd/coach/commands/migration.py --contract <path>   # Generate specific
    python atdd/coach/commands/migration.py --validate          # Check coverage only
"""

import argparse
import json
from datetime import datetime
from pathlib import Path


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS_DIR = REPO_ROOT / "contracts"
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"


def contract_needs_migration(contract_path: Path) -> bool:
    """
    Determine if a contract needs a database migration.

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

        # Rule 3: Event without id
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

        # Rule 7: Conservative default
        if metadata.get("to") == "external" and len(properties) > 0:
            return True

        # Rule 8: Fallback
        return False

    except Exception as e:
        print(f"Warning: Could not parse {contract_path}: {e}")
        return True  # Conservative: assume needs migration


def derive_table_name_from_contract(contract_path: Path) -> str:
    """Derive table name from contract path: {theme}_{domain}_{aspect}"""
    # Try relative to CONTRACTS_DIR first
    try:
        relative_path = contract_path.relative_to(CONTRACTS_DIR)
        parts = relative_path.parts
    except ValueError:
        # Fallback: parse from path structure (for tests)
        # Assume path is .../contracts/{theme}/{domain}/{aspect}.schema.json
        parts = contract_path.parts
        contracts_idx = parts.index("contracts") if "contracts" in parts else -4
        parts = parts[contracts_idx + 1:]

    theme = parts[0]
    domain = parts[1]
    aspect = contract_path.stem.replace(".schema", "")

    return f"{theme}_{domain}_{aspect}".replace("-", "_")


def generate_migration_sql(contract_path: Path) -> str:
    """
    Generate standard JSONB blob table migration.

    All tables use same structure:
    - id UUID PRIMARY KEY
    - data JSONB NOT NULL (stores entire contract)
    - created_at, updated_at timestamps
    - GIN index on data
    - Table comment with contract $id for traceability
    """
    with open(contract_path, 'r') as f:
        contract = json.load(f)

    table_name = derive_table_name_from_contract(contract_path)
    contract_id = contract.get("$id", "unknown")

    # Standard JSONB table template
    try:
        path_display = str(contract_path.relative_to(REPO_ROOT))
    except ValueError:
        path_display = contract_path.name

    sql = f"""-- Generated from {path_display}
-- Contract: {contract_id}
-- Generated: {datetime.now().isoformat()}
-- JSONB-first storage strategy (see migration.convention.yaml)

CREATE TABLE IF NOT EXISTS {table_name} (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_{table_name}_data ON {table_name} USING GIN (data);

COMMENT ON TABLE {table_name} IS 'Contract: {contract_id}. JSONB blob storage for wagon architecture.';
"""

    return sql


def main():
    parser = argparse.ArgumentParser(description="Generate Supabase JSONB migrations from contracts")
    parser.add_argument("--contract", type=Path, help="Specific contract to generate migration for")
    parser.add_argument("--validate", action="store_true", help="Only validate coverage, don't generate")

    args = parser.parse_args()

    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)

    if args.validate:
        print("Validating migration coverage...")
        print("Run: pytest atdd/tester/test_migration_coverage.py")
        return

    # Generate for specific contract
    if args.contract:
        if not args.contract.exists():
            print(f"Error: Contract not found: {args.contract}")
            return

        if not contract_needs_migration(args.contract):
            print(f"ℹ️  Contract does not need migration (strategy='none' or transient)")
            return

        migration_sql = generate_migration_sql(args.contract)
        table_name = derive_table_name_from_contract(args.contract)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{table_name}.sql"
        output_path = MIGRATIONS_DIR / filename

        output_path.write_text(migration_sql)
        print(f"✅ Generated: {output_path.relative_to(REPO_ROOT)}")
        print(f"📦 JSONB blob storage - no manual review needed")
        print(f"🚀 Apply: supabase db push")
        return

    # Generate all missing migrations
    print("Scanning contracts for missing migrations...")

    contracts = list(CONTRACTS_DIR.rglob("*.schema.json"))
    generated = 0
    skipped = 0

    for contract in contracts:
        relative_path = contract.relative_to(CONTRACTS_DIR)
        parts = relative_path.parts

        if len(parts) < 3:
            continue

        if not contract_needs_migration(contract):
            skipped += 1
            continue

        table_name = derive_table_name_from_contract(contract)

        # Check if migration exists
        has_migration = any(
            f"CREATE TABLE {table_name}" in mig.read_text() or
            f"CREATE TABLE IF NOT EXISTS {table_name}" in mig.read_text()
            for mig in MIGRATIONS_DIR.glob("*.sql")
        )

        if not has_migration:
            migration_sql = generate_migration_sql(contract)

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            filename = f"{timestamp}_{table_name}.sql"
            output_path = MIGRATIONS_DIR / filename

            output_path.write_text(migration_sql)
            print(f"✅ Generated: {output_path.relative_to(REPO_ROOT)}")
            generated += 1

    print(f"\n✅ Generated {generated} JSONB migrations")
    if skipped > 0:
        print(f"ℹ️  Skipped {skipped} non-persistent contracts")
    print(f"📦 All use standard JSONB blob storage")
    print(f"🚀 Apply: supabase db push")
    print(f"\nValidate: pytest atdd/tester/test_migration_coverage.py")


if __name__ == "__main__":
    main()
