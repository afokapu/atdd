# URN: test:author-atdd-substrate:substrate-spine:K001-SMOKE-001-authored-artifact-not-rejected
# Acceptance: acc:author-atdd-substrate:K001-SMOKE-001-authored-artifact-not-rejected
# WMBT: wmbt:author-atdd-substrate:K001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""K001-SMOKE-001 — real-CLI-authored artifacts are well-formed and carry no bypass marker.

No consuming validator reads these kinds yet (loader deferred to #1102), so
"atdd validate does not flag the new paths" is measured here as: each artifact
the real CLI writes is schema-valid against its on-disk schema and contains no
authoring-only suppression/bypass marker that could perturb validation.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import validate

from atdd.planner.commands.author_schemas import load_schema

_SRC = Path(__file__).resolve().parents[4]
_FORBIDDEN = ["atdd:suppress", "skip-permissions", "dangerously", "BYPASS"]


def _cli(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    r = subprocess.run([sys.executable, "-m", "atdd", "author", *args],
                       cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r


def test_real_cli_artifacts_are_well_formed_and_markerless(tmp_path):
    node = tmp_path / "n.yaml"
    _cli(["convention-node", "--role", "coder", "--rule-id", "coder.green.x",
          "--statement", "s", "--term", "t=y"], tmp_path)
    node = tmp_path / "src/atdd/coder/conventions/nodes/coder.green.x.convention.yaml"
    rel = tmp_path / "relationships.yaml"
    _cli(["relationship", "--source", "coder.green.a", "--type", "enables",
          "--target", "coder.green.b", "--path", str(rel)], tmp_path)
    scope = tmp_path / "scopes.yaml"
    _cli(["scope", "--scope-id", "scope.source.python", "--selector",
          "path_glob=src/**/*.py", "--path", str(scope)], tmp_path)
    gate = tmp_path / "post-commit.yaml"
    _cli(["gate", "--gate-id", "gate.post_commit.x", "--trigger-type", "git_hook",
          "--trigger-name", "post-commit", "--selection", "blast_radius",
          "--action", "never_block", "--path", str(gate)], tmp_path)

    validate(yaml.safe_load(node.read_text()), load_schema("convention-node"))
    for e in yaml.safe_load(rel.read_text())["edges"]:
        validate(e, load_schema("relationship"))
    for s in yaml.safe_load(scope.read_text())["scopes"]:
        validate(s, load_schema("scope"))
    for g in yaml.safe_load(gate.read_text())["gates"]:
        validate(g, load_schema("gate"))

    for path in (node, rel, scope, gate):
        text = path.read_text()
        for marker in _FORBIDDEN:
            assert marker not in text, f"{path.name} has bypass marker {marker!r}"
