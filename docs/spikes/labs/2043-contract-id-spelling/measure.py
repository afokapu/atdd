"""Lab measurement: what does the traceability graph actually say about a
create_contract-authored contract? Prints facts only; no assertions."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from atdd.coach.utils.graph.graph_builder import GraphBuilder
from atdd.coach.utils.graph.edge_validator import EdgeValidator
from atdd.coach.utils.graph.resolver import ResolverRegistry


def main(root: Path) -> int:
    # Discovered, not hardcoded: this harness is run against several worlds and
    # an earlier version crashed on every world but the first.
    for schema in sorted((root / "contracts").rglob("*.schema.json")):
        print(f"schema path            : {schema.relative_to(root)}")
        print(f"schema $id             : {json.loads(schema.read_text())['$id']!r}")

    reg = yaml_load(root / "contracts" / "_contracts.yaml")
    for entry in reg.get("contracts", []):
        print(f"registry identity      : {entry['identity']!r}")

    for manifest_path in sorted((root / "plan").rglob("_*.yaml")):
        manifest = yaml_load(manifest_path)
        for item in manifest.get("produce", []) or []:
            print(f"manifest produce[].contract : {item.get('contract')!r}")

    builder = GraphBuilder(repo_root=root, use_cache=False)
    graph = builder.build()

    contract_nodes = sorted(n.urn for n in graph.nodes_by_family("contract"))
    print(f"graph contract NODES   : {contract_nodes}")

    edges = [
        (e.source_urn, e.edge_type.value, e.target_urn)
        for e in graph.edges
        if e.edge_type.value in ("produces", "consumes")
    ]
    print(f"graph produce/consume EDGES : {sorted(edges)}")

    validator = EdgeValidator(graph)
    result = validator.validate_contracts()
    print(f"validate_contracts issues   : {len(result.issues)}")
    for issue in result.issues:
        print(f"  - [{issue.severity.value}] {issue.urn} :: {issue.message}")

    # Does the node URN resolve back to the file it came from?
    registry = ResolverRegistry(root)
    for urn in contract_nodes:
        res = registry.resolve(urn)
        print(f"resolve({urn!r}) -> paths={[str(p.relative_to(root)) for p in res.resolved_paths]} error={res.error!r}")

    return 0


def yaml_load(p: Path):
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
