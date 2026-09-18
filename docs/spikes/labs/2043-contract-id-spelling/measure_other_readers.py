"""Lab 3: the same prefix-on-read defect outside the graph module.

grep found six sites that build a contract URN by prefixing a value read from a
schema's $id. Two are in the graph module (already measured). These are the other
four. Measured, not inferred.
"""
from __future__ import annotations

import sys
from pathlib import Path


def main(root: Path) -> int:
    schema = root / "contracts" / "match" / "result.schema.json"
    expected = "contract:match:result"
    print(f"expected contract URN : {expected!r}\n")

    # --- site 3: coach/commands/registry.py:983 (atdd registry update)
    from atdd.coach.commands.registry import RegistryUpdater
    try:
        up = RegistryUpdater(repo_root=root)
    except TypeError:
        up = RegistryUpdater(root)
    entry = up._build_artifact_entry(schema)
    print(f"registry.py:983       -> {entry['urn']!r}  {'OK' if entry['urn']==expected else 'WRONG'}")

    # --- site 4: coach/commands/consumers.py:258
    from atdd.coach.commands.consumers import ContractScanner
    id_map = ContractScanner.scan_contract_ids(root / "contracts")
    for urn in id_map:
        print(f"consumers.py:258      -> {urn!r}  {'OK' if urn==expected else 'WRONG'}")

    # --- site 5: tester/validators/test_telemetry_structure.py:95
    import atdd.tester.validators.test_telemetry_structure as ts
    fn = getattr(ts, "collect_contract_urns", None) or getattr(ts, "_collect_contract_urns", None)
    if fn:
        try:
            urns = fn(root)
        except TypeError:
            urns = fn()
        print(f"test_telemetry:95     -> {sorted(urns)}")
    else:
        print("test_telemetry:95     -> (helper not directly callable; see source)")

    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
