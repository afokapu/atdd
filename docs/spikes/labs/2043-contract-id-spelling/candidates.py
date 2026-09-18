"""Lab: score candidate fixes by monkeypatching the REAL reader methods and
re-running the REAL graph build + validator. The code path executes; only the
world is disposable.

Candidate 1 - blind strip : urn = "contract:" + $id.removeprefix("contract:")
Candidate 3 - path-derived: identity comes from the file's location under
              contracts/, which _contract_paths() derives deterministically
              from the identity; $id is not trusted for identity at all.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from atdd.coach.utils.graph import resolver as resolver_mod
from atdd.coach.utils.graph import graph_builder as gb_mod
from atdd.coach.utils.graph.graph_builder import GraphBuilder
from atdd.coach.utils.graph.edge_validator import EdgeValidator

PREFIX = "contract:"


def _strip(identity: str) -> str:
    identity = (identity or "").strip()
    return identity[len(PREFIX):] if identity.startswith(PREFIX) else identity


def install_candidate_1() -> None:
    """Readers normalize: strip one optional leading `contract:` from $id."""
    orig_decl = resolver_mod.ContractResolver._contract_declaration

    def patched_decl(self, contract_file):
        decl = orig_decl(self, contract_file)
        if decl is None:
            return None
        decl.urn = f"{PREFIX}{_strip(decl.urn[len(PREFIX):])}"
        return decl

    resolver_mod.ContractResolver._contract_declaration = patched_decl

    orig_from_schema = gb_mod.GraphBuilder._contract_urn_from_schema

    def patched_from_schema(self, contract_path):
        urn = orig_from_schema(self, contract_path)
        return None if urn is None else f"{PREFIX}{_strip(urn[len(PREFIX):])}"

    gb_mod.GraphBuilder._contract_urn_from_schema = patched_from_schema


def install_candidate_3(root: Path) -> None:
    """Readers derive identity from the schema's path under contracts/."""
    def patched_decl(self, contract_file):
        try:
            data = json.loads(Path(contract_file).read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        sid = data.get("$id")
        if not sid or sid.startswith("urn:jel:"):
            return None
        rel = Path(contract_file).relative_to(self.contracts_dir)
        identity = str(rel).replace(".schema.json", "").replace("/", ":")
        return resolver_mod.URNDeclaration(
            urn=f"{PREFIX}{identity}",
            family="contract",
            source_path=Path(contract_file),
            context="contract schema",
        )

    resolver_mod.ContractResolver._contract_declaration = patched_decl

    def patched_from_schema(self, contract_path):
        p = Path(contract_path)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        sid = data.get("$id") if isinstance(data, dict) else None
        if not sid or sid.startswith("urn:jel:"):
            return None
        rel = p.relative_to(self.repo_root / "contracts")
        identity = str(rel).replace(".schema.json", "").replace("/", ":")
        return f"{PREFIX}{identity}"

    gb_mod.GraphBuilder._contract_urn_from_schema = patched_from_schema



def install_candidate_4() -> None:
    """E1 transitional reader: an $id that is ALREADY a well-formed contract URN
    is the node URN as-is; a bare identity is still prefixed. Ambiguous only for
    a bare identity whose theme is literally `contract` — which the E1 migration
    removes permanently."""
    from atdd.coach.utils.graph.urn import URNGrammar as URNBuilder

    def _urn_for(schema_id: str) -> str:
        if schema_id.startswith(PREFIX) and URNBuilder.validate_urn(schema_id, "contract"):
            return schema_id
        return f"{PREFIX}{schema_id}"

    orig_decl = resolver_mod.ContractResolver._contract_declaration

    def patched_decl(self, contract_file):
        decl = orig_decl(self, contract_file)
        if decl is None:
            return None
        decl.urn = _urn_for(decl.urn[len(PREFIX):])
        return decl

    resolver_mod.ContractResolver._contract_declaration = patched_decl

    orig_from_schema = gb_mod.GraphBuilder._contract_urn_from_schema

    def patched_from_schema(self, contract_path):
        urn = orig_from_schema(self, contract_path)
        return None if urn is None else _urn_for(urn[len(PREFIX):])

    gb_mod.GraphBuilder._contract_urn_from_schema = patched_from_schema


def install_resolve_prefix_fix() -> None:
    """Strip the family prefix ONCE, not every occurrence (resolver.py:756)."""
    def patched_resolve(self, urn):
        if not self.can_resolve(urn):
            return resolver_mod.URNResolution(urn=urn, family=self.family, error="Not a contract URN")
        error = self._validate_urn_format(urn)
        if error:
            return resolver_mod.URNResolution(urn=urn, family=self.family, error=error)
        contract_id = urn[len(PREFIX):] if urn.startswith(PREFIX) else urn
        paths = self._find_contract_files(contract_id)
        return resolver_mod.URNResolution(
            urn=urn, family=self.family, resolved_paths=paths,
            is_deterministic=len(paths) == 1,
            error=None if paths else f"Contract schema not found for: {urn}",
        )

    resolver_mod.ContractResolver.resolve = patched_resolve


def install_normalize_both_sides() -> None:
    """Candidate `n`: compare a NORMALIZED id on both sides in _find_contract_files,
    exactly as contract_resolution.py:106,111 already does. Strip-once fixes the
    URN; this fixes the comparison against a FILE whose own $id still carries a
    prefix — the transition-window case."""
    orig = resolver_mod.ContractResolver._find_contract_files

    def patched(self, contract_id):
        target = _strip(contract_id)
        paths = []
        if not self.contracts_dir.exists():
            return paths
        import json
        for f in self.contracts_dir.rglob("*.schema.json"):
            try:
                file_id = json.load(open(f, encoding="utf-8")).get("$id", "")
            except Exception:
                continue
            if file_id.startswith("urn:jel:"):
                continue
            fid = _strip(file_id)
            if fid == target or fid.replace(".", ":") == target.replace(".", ":"):
                paths.append(f)
                continue
            rel = str(f.relative_to(self.contracts_dir)).replace(".schema.json", "")
            if rel == target.replace(":", "/"):
                paths.append(f)
        return paths

    resolver_mod.ContractResolver._find_contract_files = patched


def measure(root: Path, label: str) -> int:
    graph = GraphBuilder(repo_root=root, use_cache=False).build()
    nodes = sorted(n.urn for n in graph.nodes_by_family("contract"))
    edges = sorted(
        (e.source_urn, e.target_urn)
        for e in graph.edges
        if e.edge_type.value == "produces"
    )
    issues = EdgeValidator(graph).validate_contracts().issues
    print(f"--- {label}")
    print(f"    contract nodes : {nodes}")
    print(f"    produces edges : {edges}")
    print(f"    issues         : {len(issues)}")
    for i in issues:
        print(f"      - [{i.severity.value}] {i.urn} :: {i.message}")
    return len(issues)


if __name__ == "__main__":
    root = Path(sys.argv[1])
    which = sys.argv[2]
    if which == "c1":
        install_candidate_1()
    elif which == "c3":
        install_candidate_3(root)
    elif which == "c4":
        install_candidate_4()
    elif which == "c4r":
        install_candidate_4()
        install_resolve_prefix_fix()
    elif which == "r":
        install_resolve_prefix_fix()
    elif which == "n":
        install_normalize_both_sides()
    elif which == "rn":
        install_resolve_prefix_fix()
        install_normalize_both_sides()
    # rc IS the signal: 0 = no issues, 1 = issues found. The first version of
    # this harness always exited 0, which made "capture rc from the command
    # itself" vacuous — the exact defect docs/spikes/README.md rule 4 names.
    sys.exit(1 if measure(root, which) else 0)
