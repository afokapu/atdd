# URN: test:author-plan-substrate:author-interlocking:E007-SMOKE-001-cli-authors-interlocking
# Acceptance: acc:author-plan-substrate:E007-SMOKE-001-cli-authors-interlocking
# WMBT: wmbt:author-plan-substrate:E007
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E007-SMOKE-001 — the real `atdd author interlocking --spec` CLI writes a
schema-valid artifact + a deduped registry entry in a checkout."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from atdd.planner.commands.tests._il_author_fixtures import (
    INTERLOCKING_ID,
    anchor_spec,
    author_route_train,
)
from atdd.planner.interlocking import load_interlocking

_SRC = Path(__file__).resolve().parents[4]


def _cli(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run([sys.executable, "-m", "atdd", "author", *args],
                          cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60)


def test_cli_authors_schema_valid_interlocking(tmp_path):
    author_route_train(tmp_path)
    spec = tmp_path / "il.yaml"
    spec.write_text(yaml.safe_dump(anchor_spec(), sort_keys=False), encoding="utf-8")

    r = _cli(["interlocking", "--spec", str(spec), "--root", str(tmp_path)], tmp_path)
    assert r.returncode == 0, r.stderr

    il_path = tmp_path / "plan" / "_trains" / "_interlockings" / "anchor-flow.yaml"
    assert il_path.exists()
    load_interlocking(il_path)  # schema-valid + digests present

    registry = yaml.safe_load(
        (tmp_path / "plan" / "_trains" / "_interlockings.yaml").read_text())
    ids = {e["interlocking_id"] for e in registry["interlockings"]}
    assert INTERLOCKING_ID in ids
