"""Workflow-template/CLI parseability lock for `atdd init` (issue #473).

Issue #473 reproducer: `atdd init --force` on 3.10.0 wrote workflow
templates that emitted `-m "not github_api"` to a `atdd validate` parser
that no longer accepts `-m`. Every consumer who re-inits after upgrade
hit `unrecognized arguments: -m` on first push to a feature branch.

This test locks the contract for the **main validate workflow**
(`.github/workflows/atdd-validate.yml`, written by `_write_workflow`):
every `atdd validate ...` `run:` line it emits must parse cleanly under
the live `atdd` argparse. We treat the template as a black box —
generate it via the real ProjectInitializer, grep the run-lines back
out, and feed each (with `--diagnostics-only` appended to short-circuit
after parse) through a real `python -m atdd` subprocess. A parse miss
manifests as exit code 2 + `unrecognized arguments` on stderr.

Phase scope (issue #473):
  - Phase 1 (this PR, 3.10.1 PATCH): the main validate workflow is fixed
    (`-m "not github_api"` → `--skip-api`); this test locks that fix.
  - Phase 2 (3.11.0 MINOR): the infra workflow (`atdd-validate-infra.yml`)
    will be fixed by introducing `--api-only`; this test will be extended
    to cover its `run:` lines and the `--skip-api`/`--api-only` exclusivity.

Run: PYTHONPATH=src python3 -m pytest -q \\
     src/atdd/coach/commands/tests/test_initializer_workflow_emission.py -v
"""
from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest
import yaml

from atdd.coach.commands.initializer import ProjectInitializer


pytestmark = [pytest.mark.platform]


REPO_ROOT = Path(__file__).resolve().parents[5]
RUN_LINE_RE = re.compile(r"^\s*run:\s*(atdd\s+validate\b.*?)$", re.MULTILINE)


def _make_initializer(tmp_path: Path) -> ProjectInitializer:
    """Set up a minimal target dir so _write_workflow can run."""
    cfg_dir = tmp_path / ".atdd"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(yaml.safe_dump({
        "github": {"repo": "owner/repo"},
    }))
    return ProjectInitializer(target_dir=tmp_path)


def _emit_main_validate_workflow(tmp_path: Path) -> Path:
    """Drive _write_workflow and return the generated atdd-validate.yml path."""
    init = _make_initializer(tmp_path)
    init._write_workflow(repo="owner/repo")
    path = tmp_path / ".github" / "workflows" / "atdd-validate.yml"
    assert path.exists(), "_write_workflow did not emit atdd-validate.yml"
    return path


def _extract_validate_run_lines(workflow_path: Path) -> List[str]:
    """Pull every `run: atdd validate ...` literal out of the generated YAML."""
    text = workflow_path.read_text()
    return [m.group(1).strip() for m in RUN_LINE_RE.finditer(text)]


def _parse_under_live_cli(cmd: str) -> subprocess.CompletedProcess:
    """Feed `cmd` (a raw bash run-line) through the live atdd argparse.

    `--diagnostics-only` is appended so a successful parse short-circuits
    in <100 ms instead of running every validator. Argparse failures still
    fire first and surface as rc=2 + `unrecognized arguments`.
    """
    tokens = shlex.split(cmd)
    assert tokens[:2] == ["atdd", "validate"], f"unexpected emit shape: {cmd!r}"
    full = [sys.executable, "-m", "atdd"] + tokens[1:] + ["--diagnostics-only"]
    return subprocess.run(
        full,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=REPO_ROOT,
    )


# ----------------------------------------------------------------------
# Tests — main validate workflow (Phase 1 scope)
# ----------------------------------------------------------------------

def test_main_workflow_emits_validate_run_lines(tmp_path):
    """Sanity: regression guard if someone deletes the validate jobs entirely."""
    cmds = _extract_validate_run_lines(_emit_main_validate_workflow(tmp_path))
    assert cmds, "expected at least one `run: atdd validate ...` line"


def test_main_workflow_run_lines_parse_under_live_cli(tmp_path):
    """Every `run: atdd validate ...` line in the main workflow must parse.

    Locks the issue #473 fix for the high-traffic gate workflow (every push
    + every PR). Phase 2 will extend this contract to the infra workflow.
    """
    cmds = _extract_validate_run_lines(_emit_main_validate_workflow(tmp_path))
    failures: List[str] = []
    for cmd in cmds:
        result = _parse_under_live_cli(cmd)
        if result.returncode == 2 and "unrecognized arguments" in result.stderr:
            tail = result.stderr.strip().splitlines()[-1]
            failures.append(f"  {cmd!r}\n    → {tail}")
    assert not failures, (
        "emitted run-lines fail the live argparse "
        "(issue #473 reproducer):\n" + "\n".join(failures)
    )


def test_main_workflow_does_not_emit_removed_dash_m_flag(tmp_path):
    """Belt-and-suspenders: explicit guard against the exact #473 regression."""
    cmds = _extract_validate_run_lines(_emit_main_validate_workflow(tmp_path))
    offenders = [c for c in cmds if re.search(r"(^|\s)-m(\s|$)", c)]
    assert not offenders, (
        "main validate workflow emits `-m FLAG` removed in 3.10.0 (#473): "
        f"{offenders!r}"
    )
