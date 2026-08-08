# URN: test:define-plans:atdd-plan-session:Y002-SMOKE-002-help-surfaces-name-the-new-stages
# Acceptance: acc:define-plans:Y002-SMOKE-002-help-surfaces-name-the-new-stages
# WMBT: wmbt:define-plans:Y002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""Y002-SMOKE-002 — the operator-visible help text moved with the enum.

Help strings are the surface an operator actually reads, and they are plain
literals that no unit test over `Step` would touch: the enum could be fully
renamed while `main-job (Define)` still printed. So this renders the REAL help
over subprocess and reads it back.

Covers the top-level `atdd plan` gloss, the per-subcommand glosses, the `ratify
(confirm)` alias as argparse displays it, and the README — which documents the
same stage names and the same `--step` values an operator would copy.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[4]
_REPO = _SRC.parent
_README = _REPO / "README.md"

NEW_STAGES = ("Intent", "Attach", "Compose", "Ratify")


def _cli(*args) -> str:
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""),
           "HOME": os.environ.get("HOME", "")}
    r = subprocess.run([sys.executable, "-m", "atdd", *args],
                       env=env, capture_output=True, text=True, timeout=120)
    return r.stdout + r.stderr


@pytest.fixture(scope="module")
def plan_help() -> str:
    return _cli("plan", "--help")


def test_the_plan_subcommand_glosses_name_the_new_stages(plan_help):
    assert "set the JTBD main job (Intent)" in plan_help
    assert "capture a source (Attach)" in plan_help
    assert "add a candidate unit (Compose)" in plan_help


def test_reopen_help_sends_the_operator_to_compose(plan_help):
    assert "return the session to Compose" in plan_help or "return to Compose" in plan_help
    assert "Prepare" not in plan_help


def test_ratify_is_listed_with_confirm_as_its_alias(plan_help):
    """argparse renders an aliased subcommand as `ratify (confirm)`."""
    assert "ratify (confirm)" in plan_help


def test_advance_help_offers_only_the_new_step_values():
    advance_help = _cli("plan", "advance", "--help")
    assert "{intent,attach,compose,ratify,authored}" in advance_help
    for retired in ("define", "locate", "prepare"):
        assert retired not in advance_help


def test_the_top_level_gloss_names_the_new_lifecycle():
    top = _cli("--help")
    assert "Intent→Attach→Compose→Ratify→author" in top
    assert "Define→Locate→Prepare→Confirm→author" not in top


@pytest.mark.parametrize("stage", NEW_STAGES)
def test_the_readme_documents_each_new_stage(stage):
    assert f"**{stage}**" in _README.read_text(encoding="utf-8")


def test_the_readme_step_values_match_what_the_cli_accepts():
    """The README must not hand an operator a command argparse now rejects."""
    readme = _README.read_text(encoding="utf-8")
    assert "--step attach|compose|ratify" in readme
    assert "--step locate|prepare|confirm" not in readme
    for retired in ("--step locate", "--step prepare", "--step confirm"):
        assert retired not in readme
