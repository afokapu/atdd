"""Lab 2: the case that separates the two candidate fixes.

A consumer repo may override the theme map (themes: block in .atdd/config.yaml,
planner.artifact-naming.theme-taxonomy). Nothing forbids a theme literally named
`contract`. Its BARE identity is then `contract:result` — textually identical to
a `contract:`-PREFIXED identity. Blind prefix-stripping cannot tell them apart.

Hand-authored (bare $id) is used here, i.e. the pre-#1330 spelling that 100% of
the toolkit's own 21 contracts use, so the file is correct and only the reader
is under test.
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

    schema_dir = root / "contracts" / "contract"
    schema_dir.mkdir(parents=True)
    (schema_dir / "result.schema.json").write_text(
        json.dumps(
            {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "$id": "contract:result",          # BARE identity, theme == "contract"
                "title": "ContractResult",
                "type": "object",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "contracts" / "_contracts.yaml").write_text(
        yaml.safe_dump({"contracts": [{
            "identity": "contract:result",
            "path": "contracts/contract/result.schema.json",
            "theme": "contract",
            "producers": ["wagon:settle-contract"],
            "consumers": [],
        }]}, sort_keys=False),
        encoding="utf-8",
    )

    wagon_dir = root / "plan" / "settle_contract"
    wagon_dir.mkdir(parents=True)
    (wagon_dir / "_settle_contract.yaml").write_text(
        yaml.safe_dump({
            "wagon": "settle-contract",
            "urn": "wagon:settle-contract",
            "name": "Settle Contract",
            "theme": "contract",
            "features": [{"urn": "feature:settle-contract:settle-contract"}],
            # The URN of a bare identity `contract:result` is the family prefix
            # plus the identity.
            "produce": [{"name": "contract:result",
                         "contract": "contract:contract:result",
                         "telemetry": None, "to": "internal"}],
        }, sort_keys=False),
        encoding="utf-8",
    )
    return root


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
