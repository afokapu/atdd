# URN: test:author-atdd-substrate:author-convention-node:variant-scaffold-smoke
# Issue: #1212
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE — the real `atdd author` CLI scaffolds a node AND an enforceable variant (#1212).

Drives the installed CLI end-to-end in a tmp checkout: a single
`convention-node --family/--template` invocation must write BOTH the rule node
and a convention-graph variant under `validators/conventions/<family>/`, and the
scaffolded variant must import the family archetype and pass its contract test
under a fresh pytest run (honest RED scaffold: contract passes, traversal xfails).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]


def _env(tmp_path: Path) -> dict:
    return {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path)}


def test_cli_scaffolds_node_and_variant(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable, "-m", "atdd", "author", "convention-node", "--core",
            "--role", "coder", "--rule-id", "coder.green.demo-x",
            "--statement", "Demo rule for the variant scaffolder smoke.",
            "--term", "x=y",
            "--implementation", '{"type":"validator","ref":"test_x::test_y"}',
            "--family", "grammar", "--template", "identifier_grammar_conformance",
            "--root", str(tmp_path),
        ],
        cwd=str(tmp_path), env=_env(tmp_path), capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr

    node = (
        tmp_path / "src" / "atdd" / "coder" / "conventions" / "nodes"
        / "coder.green.demo-x.convention.yaml"
    )
    variant = (
        tmp_path / "src" / "atdd" / "validators" / "conventions" / "grammar"
        / "test_coder_green_demo_x.py"
    )
    assert node.exists(), f"node not created\n{result.stderr}"
    assert variant.exists(), f"variant not scaffolded\n{result.stderr}"
    assert "# Phase: RED" in variant.read_text(encoding="utf-8")

    # the scaffolded variant imports the family archetype and passes its contract
    # test under a fresh interpreter (1 passed, 1 xfailed — no failures).
    run = subprocess.run(
        [sys.executable, "-m", "pytest", str(variant), "-q"],
        cwd=str(tmp_path), env=_env(tmp_path), capture_output=True, text=True, timeout=120,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "1 passed" in run.stdout and "1 xfailed" in run.stdout, run.stdout


def test_cli_half_given_family_is_rejected_without_writing(tmp_path) -> None:
    # --family without --template must fail and leave NO node behind (validated
    # before any write).
    result = subprocess.run(
        [
            sys.executable, "-m", "atdd", "author", "convention-node", "--core",
            "--role", "coder", "--rule-id", "coder.green.demo-y",
            "--statement", "Demo.", "--term", "x=y",
            "--implementation", '{"type":"validator","ref":"a::b"}',
            "--family", "grammar",
            "--root", str(tmp_path),
        ],
        cwd=str(tmp_path), env=_env(tmp_path), capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 2, result.stdout
    node = (
        tmp_path / "src" / "atdd" / "coder" / "conventions" / "nodes"
        / "coder.green.demo-y.convention.yaml"
    )
    assert not node.exists(), "a rejected variant request must not leave a stray node"
