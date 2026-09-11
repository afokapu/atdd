# URN: test:author-plan-substrate:author-train:E004-SMOKE-002-cli-reauthors-an-existing-train
# Acceptance: acc:author-plan-substrate:E004-SMOKE-002-cli-reauthors-an-existing-train
# WMBT: wmbt:author-plan-substrate:E004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E004-SMOKE-002 — the real `atdd author train` CLI lands a re-authored spec.

Drives the CLI twice against a checkout, with the manifest gaining post-authoring
state in between. The unit tests pin `create_train` directly; this one proves the
operator's actual command does it, because the path that was broken is the one
the operator is TOLD to take: `PlanSession.reopen()` refuses once step ==
AUTHORED and directs them to author the change as a new plan session, which
dispatches straight back through this CLI (#1915).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

_SRC = Path(__file__).resolve().parents[4]

TRAIN_ID = "train:issue-lifecycle:smoke-reauthor"
MANIFEST = Path("plan") / "_trains" / "issue-lifecycle" / "smoke-reauthor.yaml"


def _cli(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run([sys.executable, "-m", "atdd", "author", *args],
                          cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60)


def _author(tmp_path, spec_doc, name):
    spec = tmp_path / name
    spec.write_text(yaml.safe_dump(spec_doc), encoding="utf-8")
    return _cli(["train", "--spec", str(spec), "--root", str(tmp_path)], tmp_path)


def _spec(description, wagons):
    return {
        "train_id": TRAIN_ID,
        "category": "nominal",
        "title": "Smoke reauthor",
        "description": description,
        "themes": ["coach"],
        "wagons": wagons,
        "sequence": [{"step": 1, "actor": f"wagon:{wagons[0]}", "action": "does the thing"}],
    }


def test_cli_reauthors_an_existing_train_without_clobbering_it(tmp_path):
    (tmp_path / "plan" / "_trains").mkdir(parents=True)
    (tmp_path / "plan" / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")

    first = _author(tmp_path, _spec("the first authoring", ["wagon-a"]), "train-v1.yaml")
    assert first.returncode == 0, first.stderr
    manifest = tmp_path / MANIFEST
    assert manifest.exists(), first.stdout + first.stderr

    # State that arrives AFTER authoring — from coach, or from a human. The writer
    # does not own it, so a re-author must carry it through.
    doc = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    doc["status"] = "tested"
    doc["route_space"] = {"classification": "single-route", "basis": "not-yet-assessed"}
    manifest.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    second = _author(
        tmp_path, _spec("the second authoring", ["wagon-a", "wagon-b"]), "train-v2.yaml"
    )
    assert second.returncode == 0, second.stderr

    after = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert after["description"] == "the second authoring", "the re-author must land"
    assert after["participants"] == ["wagon:wagon-a", "wagon:wagon-b"]
    assert after["status"] == "tested", "a re-author must not reset the phase"
    assert after["route_space"] == doc["route_space"], "post-authoring state must survive"

    registry = yaml.safe_load((tmp_path / "plan" / "_trains.yaml").read_text(encoding="utf-8"))
    rows = [
        entry
        for buckets in registry["trains"].values()
        for entries in buckets.values()
        for entry in entries
        if entry["train_id"] == TRAIN_ID
    ]
    assert len(rows) == 1, f"one train_id must yield one registry row; got {len(rows)}"
    assert rows[0]["description"] == "the second authoring"
    assert rows[0]["wagons"] == ["wagon-a", "wagon-b"]
