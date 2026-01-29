#!/usr/bin/env python3
"""
Infer and set governance.status for contract schemas.

Inference rules:
- version 0.x.x → "draft" (still iterating)
- wagon_ref = "plan/unknown/_unknown.yaml" → "draft" (no real wagon)
- version 1.x.x+ with real wagon → "active" (stable)

Usage:
    python3 atdd/coach/commands/infer_governance_status.py [--dry-run]
"""

import sys
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS_DIR = REPO_ROOT / "contracts"


def infer_status(contract: dict) -> str:
    """Infer governance status from contract metadata."""
    version = contract.get("version", "0.0.0")
    metadata = contract.get("x-artifact-metadata", {})
    traceability = metadata.get("traceability", {})
    wagon_ref = traceability.get("wagon_ref", "")

    # Rule 1: Version-based
    if version.startswith("0."):
        return "draft"

    # Rule 2: Traceability-based
    if wagon_ref == "plan/unknown/_unknown.yaml" or not wagon_ref:
        return "draft"

    # Rule 3: Active (1.x.x+ with real wagon)
    return "active"


def infer_stability(contract: dict, status: str) -> str:
    """Infer governance stability."""
    if status == "draft":
        return "experimental"

    # For active contracts, use stable (meta-schema only allows: experimental, stable, frozen)
    return "stable"


def set_governance_status(contract_path: Path, dry_run: bool = False) -> dict:
    """Set governance.status for a contract."""
    try:
        with open(contract_path) as f:
            contract = json.load(f)

        metadata = contract.get("x-artifact-metadata", {})
        if not metadata:
            return {"status": "skip", "reason": "No x-artifact-metadata"}

        governance = metadata.get("governance", {})

        # Infer status
        inferred_status = infer_status(contract)
        inferred_stability = infer_stability(contract, inferred_status)

        current_status = governance.get("status")
        current_stability = governance.get("stability")

        # Check if update needed
        changes = []
        if current_status != inferred_status:
            governance["status"] = inferred_status
            changes.append(f"status: {current_status} → {inferred_status}")

        if current_stability != inferred_stability:
            governance["stability"] = inferred_stability
            changes.append(f"stability: {current_stability} → {inferred_stability}")

        if not changes:
            return {"status": "skip", "reason": "Already correct"}

        # Update contract
        metadata["governance"] = governance
        contract["x-artifact-metadata"] = metadata

        if not dry_run:
            with open(contract_path, 'w') as f:
                json.dump(contract, f, indent=2)
                f.write('\n')

        return {
            "status": "updated",
            "changes": changes
        }

    except Exception as e:
        return {"status": "error", "reason": str(e)}


def main():
    """Infer governance status for all contracts."""
    dry_run = "--dry-run" in sys.argv
    mode = "DRY RUN" if dry_run else "APPLY CHANGES"

    print("=" * 80)
    print(f"Infer Governance Status for Contracts ({mode})")
    print("=" * 80)
    print()

    contract_files = list(CONTRACTS_DIR.rglob("*.schema.json"))

    updated = 0
    skipped = 0
    errors = 0

    for contract_path in sorted(contract_files):
        result = set_governance_status(contract_path, dry_run)

        if result["status"] == "updated":
            rel_path = contract_path.relative_to(REPO_ROOT)
            print(f"✅ {rel_path}")
            for change in result["changes"]:
                print(f"   {change}")
            updated += 1
        elif result["status"] == "skip":
            skipped += 1
        elif result["status"] == "error":
            print(f"❌ {contract_path.relative_to(REPO_ROOT)}: {result['reason']}")
            errors += 1

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total contracts: {len(contract_files)}")
    print(f"✅ Updated: {updated}")
    print(f"⏭️  Skipped: {skipped}")
    print(f"❌ Errors: {errors}")
    print("=" * 80)

    if dry_run:
        print()
        print("This was a DRY RUN. No files were modified.")
        print("Run without --dry-run to apply changes:")
        print("  python3 atdd/coach/commands/infer_governance_status.py")


if __name__ == "__main__":
    main()
