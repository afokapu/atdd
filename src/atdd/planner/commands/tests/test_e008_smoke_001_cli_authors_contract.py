# URN: test:author-plan-substrate:author-contract:E008-SMOKE-001-cli-authors-contract
# Acceptance: acc:author-plan-substrate:E008-SMOKE-001-cli-authors-contract
# WMBT: wmbt:author-plan-substrate:E008
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E008-SMOKE-001 — the real `atdd author contract --spec` CLI writes a
schema-valid contract file (draft-07, $id contract:{identity}) and a deduped
registry entry in a checkout, no manual patching."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

_SRC = Path(__file__).resolve().parents[4]


def _cli(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    return subprocess.run([sys.executable, "-m", "atdd", "author", *args],
                          cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60)


def test_cli_authors_schema_valid_contract(tmp_path):
    spec = tmp_path / "contract.yaml"
    spec.write_text(yaml.safe_dump({
        "identity": "commons:error:probe-response",
        "title": "CommonsErrorProbeResponse",
        "description": "a probe error response",
        "producer": "wagon:govern-lifecycle",
    }, sort_keys=False), encoding="utf-8")

    r = _cli(["contract", "--spec", str(spec), "--root", str(tmp_path)], tmp_path)
    assert r.returncode == 0, r.stderr

    schema_path = tmp_path / "contracts" / "commons" / "error" / "probe-response.schema.json"
    assert schema_path.exists()
    doc = json.loads(schema_path.read_text(encoding="utf-8"))
    assert doc["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert doc["$id"] == "contract:commons:error:probe-response"

    registry = yaml.safe_load((tmp_path / "contracts" / "_contracts.yaml").read_text())
    ids = {e["id"] for e in registry["contracts"]}
    assert "commons:error:probe-response" in ids
