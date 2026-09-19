"""Lab 4 (world4): a create_contract-authored contract NOT at its convention path.

`contract_resolution.py:101-115` deliberately supports a correctly-identified
schema at a non-canonical location. This world asks whether the resolver fix
survives that — i.e. whether stripping the prefix off the URN is enough when the
FILE's own $id still carries one.
"""
from __future__ import annotations
import shutil, sys
from pathlib import Path
import yaml
from atdd.planner.commands.author import create_contract


def build(root: Path) -> Path:
    if root.exists(): shutil.rmtree(root)
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    (root / "contracts").mkdir(); (root / "plan").mkdir()

    p = create_contract({"identity": "match:result", "title": "MatchResult",
                         "producers": ["wagon:score-match"]}, root=root)
    # Move it off the convention path; identity and manifest unchanged.
    dest = root / "contracts" / "shared" / "v1" / "match-result.schema.json"
    dest.parent.mkdir(parents=True)
    shutil.move(str(p), str(dest))

    w = root / "plan" / "score_match"; w.mkdir(parents=True)
    (w / "_score_match.yaml").write_text(yaml.safe_dump({
        "wagon": "score-match", "urn": "wagon:score-match", "name": "Score Match",
        "theme": "match", "features": [{"urn": "feature:score-match:score-match"}],
        "produce": [{"name": "match:result", "contract": "contract:match:result",
                     "telemetry": None, "to": "internal"}],
    }, sort_keys=False), encoding="utf-8")
    return root


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
