"""Lab: build a throwaway consumer repo the way a consumer repo is actually built.

Real code path under test: create_contract (the authoring writer) -> the files on
disk -> TraceabilityGraphBuilder (the reader). Nothing about either is stubbed.
Only the *world* is disposable.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import yaml

from atdd.planner.commands.author import create_contract


def build(root: Path) -> Path:
    if root.exists():
        shutil.rmtree(root)
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    (root / "contracts").mkdir()
    (root / "plan").mkdir()

    # 1. Author the contract through the REAL writer, exactly as a consumer repo
    #    does via `atdd author contract`.
    create_contract(
        {
            "identity": "match:result",
            "title": "MatchResult",
            "description": "the result of a match",
            "version": "1.0.0",
            "producers": ["wagon:score-match"],
            "consumers": ["wagon:rank-players"],
        },
        root=root,
    )

    # 2. The wagon manifest that names it, in the shape the repo's own manifests
    #    use (plan/<wagon>/_<wagon>.yaml, `produce[].contract` = the URN).
    wagon_dir = root / "plan" / "score_match"
    wagon_dir.mkdir(parents=True)
    (wagon_dir / "_score_match.yaml").write_text(
        yaml.safe_dump(
            {
                "wagon": "score-match",
                "urn": "wagon:score-match",
                "name": "Score Match",
                "theme": "match",
                "features": [{"urn": "feature:score-match:score-match"}],
                "produce": [
                    {"name": "match:result", "contract": "contract:match:result",
                     "telemetry": None, "to": "internal"}
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return root


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
