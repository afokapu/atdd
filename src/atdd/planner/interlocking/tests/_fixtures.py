"""Shared fixtures: write a self-consistent interlocking + train tree under a root.

These helpers materialize the canonical homes from issue #1248 so the loader,
guard, route-resolution, digest, and projection tests all exercise the real
on-disk shape rather than ad-hoc dicts.

The shape is the typed post-#1421 one: trains carry a ``train:<subject>:<slug>``
identity and declare their variant classification as a ``category`` FIELD, and a
route names that category directly. Nothing here carries a classification digit —
neither in an identity nor as the retired ``category_digit`` key (#1440).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

NOMINAL_TRAIN_ID = "train:match-resolution:standard"
NOMINAL_TRAIN_PATH = "plan/_trains/match-resolution/standard.yaml"
ALTERNATE_TRAIN_ID = "train:match-resolution:timeout"
ALTERNATE_TRAIN_PATH = "plan/_trains/match-resolution/timeout.yaml"


def _train(train_id: str, category: str, intent: str, artifact: str) -> Dict[str, Any]:
    return {
        "train_id": train_id,
        "title": f"Train {train_id}",
        "description": f"Linear train {train_id} for interlocking projection tests.",
        "category": category,
        "themes": ["match"],
        "participants": ["wagon:blitz", "wagon:player"],
        "sequence": [
            {
                "step": 1,
                "intent": intent,
                "from": "wagon:blitz",
                "to": "wagon:player",
                "artifact": artifact,
            }
        ],
    }


def interlocking_doc() -> Dict[str, Any]:
    """A valid interlocking document (pre-digest fields are placeholders)."""
    return {
        "schema_version": "1.0.0",
        "interlocking_id": "interlocking:match-resolution",
        "title": "Match resolution route interlocking",
        "theme": "match",
        "status": "draft",
        "source": {
            "path": "plan/_trains/_interlockings/match-resolution.yaml",
            "content_digest": "PLACEHOLDER",
        },
        "entrypoint": {
            "exposed": True,
            "actions": ["resolve_match"],
            "reason": None,
        },
        "route_resolution": {"strategy": "fail_on_multiple_match"},
        "lifelines": [
            {"ref": "wagon:blitz"},
            {"ref": "wagon:player"},
            {"ref": "system:clock"},
        ],
        "messages": [
            {
                "id": "msg:emit-match-result",
                "kind": "boundary",
                "from": "wagon:blitz",
                "to": "wagon:player",
                "intent": "Emit result after the match is closed",
                "feature_refs": ["feature:emit-match-result"],
                "payload": {"contract": "match:result", "no_payload_reason": None},
            },
            {
                "id": "msg:tick-clock",
                "kind": "self",
                "from": "system:clock",
                "to": "system:clock",
                "intent": "Advance the match countdown clock",
                "payload": {"contract": None, "no_payload_reason": "internal timer tick"},
            },
        ],
        "fragments": [
            {
                "id": "frag:quorum-or-timeout",
                "kind": "alt",
                "acceptance_refs": ["acceptance:closes-on-quorum-or-timeout"],
                "guards": [
                    {"id": "guard:all-voted", "expression": "all_players_voted == true"},
                    {"id": "guard:timer-expires", "expression": "timer_expired == true"},
                ],
            }
        ],
        "invariants": [
            {
                "id": "inv:unresolved-max-seven",
                "wmbt_ref": "wmbt:pressure-collapse",
                "expression": "unresolved_count <= 7",
            }
        ],
        "residuals": [
            {
                "id": "residual:blitz-owns-no-grid",
                "kind": "structural",
                "acceptance_ref": "acceptance:blitz-owns-no-grid",
                "validator_ref": "src/atdd/validators/architecture/test_blitz_owns_no_grid.py",
                "reason": "no honest flow representation; structural ownership invariant",
            }
        ],
        "routes": [
            {
                "route_id": "nominal-all-voted",
                "category": "nominal",
                "priority": 10,
                "guard_ref": "guard:all-voted",
                "train_id": NOMINAL_TRAIN_ID,
                "train_path": NOMINAL_TRAIN_PATH,
                "projection": {
                    "expected_sequence_digest": "PLACEHOLDER",
                    "fields": ["step", "intent", "from", "to", "artifact"],
                },
            },
            {
                "route_id": "alternate-timeout",
                "category": "alternate",
                "priority": 20,
                "guard_ref": "guard:timer-expires",
                "train_id": ALTERNATE_TRAIN_ID,
                "train_path": ALTERNATE_TRAIN_PATH,
                "projection": {"expected_sequence_digest": "PLACEHOLDER"},
            },
        ],
    }


def write_tree(root: Path, doc: Dict[str, Any] | None = None) -> Path:
    """Materialize trains + the interlocking under ``root``; return interlocking path.

    The two route trains are written so route projection digests can be computed.
    """
    doc = doc if doc is not None else interlocking_doc()
    trains_dir = root / "plan" / "_trains"
    il_dir = trains_dir / "_interlockings"
    il_dir.mkdir(parents=True, exist_ok=True)

    for train_path, train in (
        (
            NOMINAL_TRAIN_PATH,
            _train(NOMINAL_TRAIN_ID, "nominal", "Close match on quorum", "match:result"),
        ),
        (
            ALTERNATE_TRAIN_PATH,
            _train(ALTERNATE_TRAIN_ID, "alternate", "Close match on timeout", "match:result"),
        ),
    ):
        target = root / train_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(train, sort_keys=False), encoding="utf-8")

    # registry shape
    (trains_dir / "_interlockings.yaml").write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "interlockings": [
                    {
                        "interlocking_id": doc["interlocking_id"],
                        "path": doc["source"]["path"],
                        "theme": doc["theme"],
                        "status": doc["status"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    il_path = il_dir / "match-resolution.yaml"
    il_path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return il_path
