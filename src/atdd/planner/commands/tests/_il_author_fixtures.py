"""Shared helpers for the E007 interlocking-authoring tests.

A minimal interlocking spec that passes ALL #1249 sanity rules (no payload
contracts -> no external schema files needed, single guard covered by a single
route, fragment carries an acceptance, no dangling invariants/residuals), plus a
helper that authors its route train via the real ``create_train`` writer (proving
the create_train -> create_interlocking sequencing).
"""
from __future__ import annotations

from pathlib import Path

from atdd.planner.commands.author import create_train

ROUTE_TRAIN_ID = "0001-anchor-nominal"
ROUTE_TRAIN_PATH = f"plan/_trains/{ROUTE_TRAIN_ID}.yaml"
INTERLOCKING_ID = "interlocking:anchor-flow"
ROUTE_ID = "nominal-go"


def anchor_spec() -> dict:
    return {
        "schema_version": "1.0.0",
        "interlocking_id": INTERLOCKING_ID,
        "title": "Anchor flow interlocking",
        "theme": "match",
        "status": "draft",
        "entrypoint": {"exposed": True, "actions": ["start_anchor"], "reason": None},
        "route_resolution": {"strategy": "fail_on_multiple_match"},
        "lifelines": [{"ref": "wagon:alpha"}, {"ref": "wagon:beta"}],
        "messages": [],
        "fragments": [
            {"id": "frag:go", "kind": "opt",
             "acceptance_refs": ["acceptance:anchor-go"],
             "guards": [{"id": "guard:go", "expression": "ready == true"}]},
        ],
        "routes": [
            {"route_id": ROUTE_ID, "category": "nominal",
             "priority": 10, "guard_ref": "guard:go",
             "train_id": ROUTE_TRAIN_ID, "train_path": ROUTE_TRAIN_PATH,
             "projection": {"expected_sequence_digest": "PENDING",
                            "fields": ["step", "intent", "from", "to", "artifact"]}},
        ],
    }


def author_route_train(root: Path) -> None:
    """Author the route's target train via the real create_train writer."""
    (root / "plan" / "_trains").mkdir(parents=True, exist_ok=True)
    (root / "plan" / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")
    create_train(
        {"train_id": ROUTE_TRAIN_ID, "wagons": ["alpha"],
         "description": "anchor route train",
         "source_interlocking": {"interlocking_id": INTERLOCKING_ID, "route_id": ROUTE_ID}},
        root=root,
    )


def kept_train_unit() -> dict:
    """A kept train unit whose spec declares the interlocking the gate must bind."""
    return {
        "ref": f"train:{ROUTE_TRAIN_ID}",
        "kind": "train",
        "verdict": "keep",
        "spec": {"source_interlocking": {"interlocking_id": INTERLOCKING_ID,
                                         "route_id": ROUTE_ID}},
    }
