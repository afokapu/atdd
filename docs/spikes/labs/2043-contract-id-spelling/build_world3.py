"""Lab 3 (world3): the counterexample codex constructed — verified here independently.

A consumer theme literally named `contract` plus a THREE-segment bare identity
`contract:match:result`. Unlike world2's two-segment `contract:result`, this
string IS a syntactically valid contract URN, so it exercises the ambiguous
branch of candidate c4 that world2 could not reach.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import yaml


def build(root: Path) -> Path:
    if root.exists():
        shutil.rmtree(root)
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text(
        yaml.safe_dump({"version": 1, "themes": {"1": "contract"}}), encoding="utf-8"
    )

    d = root / "contracts" / "contract" / "match"
    d.mkdir(parents=True)
    (d / "result.schema.json").write_text(json.dumps({
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "contract:match:result",   # BARE identity; theme == "contract"
        "title": "ContractMatchResult",
        "version": "1.0.0",
        "type": "object",
    }, indent=2), encoding="utf-8")

    (root / "contracts" / "_contracts.yaml").write_text(yaml.safe_dump({"contracts": [{
        "identity": "contract:match:result",
        "path": "contracts/contract/match/result.schema.json",
        "theme": "contract",
        "producers": ["wagon:settle-contract"],
        "consumers": [],
    }]}, sort_keys=False), encoding="utf-8")

    w = root / "plan" / "settle_contract"
    w.mkdir(parents=True)
    (w / "_settle_contract.yaml").write_text(yaml.safe_dump({
        "wagon": "settle-contract",
        "urn": "wagon:settle-contract",
        "name": "Settle Contract",
        "theme": "contract",
        "features": [{"urn": "feature:settle-contract:settle-contract"}],
        # family prefix + bare identity — the required URN spelling
        "produce": [{"name": "contract:match:result",
                     "contract": "contract:contract:match:result",
                     "telemetry": None, "to": "internal"}],
    }, sort_keys=False), encoding="utf-8")
    return root


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
