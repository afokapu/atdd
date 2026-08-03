# URN: test:train:0003-author-substrate:E2E-001-author-all-substrate-kinds
# Train: train:0003-author-substrate
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: End-to-end journey for the author-atdd-substrate train — the real
#          `atdd author` CLI authors one artifact of EVERY substrate kind into a
#          real tmp checkout, and each is schema-valid against its on-disk
#          canonical schema. No mocks: real subprocess, real schemas.
"""Train-level E2E: the full `atdd author` substrate-authoring journey.

Exercises the whole capability in one flow — convention-node (per-file,
conflict-free) + relationship + scope + gate (registry-class) — proving the
spine, the four writers, and the canonical schemas compose into a working
substrate-authoring journey.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import validate

from atdd.planner.commands.author_schemas import load_schema

_SRC = Path(__file__).resolve().parents[2] / "src"


def _author(args, cwd):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(cwd)}
    r = subprocess.run([sys.executable, "-m", "atdd", "author", *args],
                       cwd=str(cwd), env=env, capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, f"{args[0]} failed: {r.stderr}"
    return r


def test_author_every_substrate_kind_end_to_end(tmp_path):
    # 1. convention-node — flat per-role file
    _author(["convention-node", "--core", "--role", "coder",
             "--rule-id", "coder.green.component-urn-marker-is",
             "--statement", "Implementation files declare the component URN marker.",
             "--term", "urn_marker=Every file declares a URN marker."], tmp_path)
    node = tmp_path / "src/atdd/coder/conventions/nodes/coder.green.component-urn-marker-is.convention.yaml"
    assert node.exists()
    validate(yaml.safe_load(node.read_text()), load_schema("convention-node"))

    # 2. relationship — registry-class, sorted-insert
    rel = tmp_path / "relationships.yaml"
    _author(["relationship", "--core", "--source", "coder.green.component-urn-marker-is#urn_marker",
             "--type", "enables", "--target", "coder.green.component-urn-matches-pattern",
             "--path", str(rel)], tmp_path)
    for e in yaml.safe_load(rel.read_text())["edges"]:
        validate(e, load_schema("relationship"))

    # 3. scope — per-file, the surface + embedded selector
    scope = tmp_path / "scope.source.python.scope.yaml"
    _author(["scope", "--core", "--scope-id", "scope.source.python", "--artifact-kind", "source_file",
             "--runtime", "python", "--platform", "local_fs",
             "--selector-id", "selector.source.python.path-glob", "--selector-type", "path_glob",
             "--include", "src/**/*.py", "--exclude", ".venv/**", "--path", str(scope)], tmp_path)
    validate(yaml.safe_load(scope.read_text()), load_schema("scope"))

    # 4. gate — per-trigger file
    gate = tmp_path / "post-commit.yaml"
    _author(["gate", "--core", "--gate-id", "gate.post_commit.local_feedback",
             "--trigger-type", "git_hook", "--trigger-name", "post-commit",
             "--selection", "blast_radius", "--action", "never_block",
             "--success-code", "0", "--failure-code", "0", "--path", str(gate)], tmp_path)
    for g in yaml.safe_load(gate.read_text())["gates"]:
        validate(g, load_schema("gate"))
