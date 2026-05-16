# URN: test:govern-lifecycle:E005-INTEGRATION-001-init-emits-only-parseable-atdd-commands
# Acceptance: acc:govern-lifecycle:E005-INTEGRATION-001-init-emits-only-parseable-atdd-commands
# WMBT: wmbt:govern-lifecycle:E005
# Phase: RED
# Layer: backend.integration
# Assertion: behavioral

"""E005-INTEGRATION-001 — after the real ``ProjectInitializer`` emits the
workflow templates, every ``run: atdd ...`` line resolves to a subcommand
the live top-level argparse declares; in particular no
``run: atdd baseline update`` line survives.

Phase RED: fails — ``initializer.py`` still emits
``run: atdd baseline update`` into the ``baseline-sync`` job of
``atdd-validate.yml`` (initializer.py:1621). ``baseline`` is not a
top-level subcommand of the 3.x CLI, so the emitted workflow fails
``invalid choice: 'baseline'`` on every push to main.

Phase GREEN: the ``baseline-sync`` emit is retired (or replaced with a
real subcommand), so no emitted ``run: atdd ...`` line references a
non-existent subcommand.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import atdd.coach.validators.test_workflow_template_command_drift as drift

pytestmark = [pytest.mark.coach]


def _emit_and_collect():
    """Emit workflows via the real initializer; return {path: [atdd lines]}."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp)
        emitted = {}
        for workflow_path in drift._emit_workflow_files(target):
            rel = workflow_path.relative_to(target)
            emitted[str(rel)] = drift._extract_atdd_run_lines(workflow_path)
        return emitted


def test_no_workflow_emits_atdd_baseline_update() -> None:
    """No emitted workflow file may contain ``run: atdd baseline update``."""
    emitted = _emit_and_collect()
    offenders = {
        path: [ln for ln in lines if shlex.split(ln)[:3] == ["atdd", "baseline", "update"]]
        for path, lines in emitted.items()
    }
    offenders = {p: v for p, v in offenders.items() if v}
    assert not offenders, (
        f"`atdd init` still emits `atdd baseline update` — a non-existent "
        f"subcommand — into: {offenders}. The baseline-sync emit must be "
        f"retired or replaced (issue #481)."
    )


def test_every_emitted_atdd_subcommand_exists_in_live_cli() -> None:
    """Each emitted ``run: atdd <sub>`` resolves to a real top-level subcommand."""
    emitted = _emit_and_collect()
    bad = []
    for path, lines in emitted.items():
        for line in lines:
            tokens = shlex.split(line)
            subcommand = tokens[1] if len(tokens) > 1 else ""
            result = subprocess.run(
                [sys.executable, "-m", "atdd", subcommand, "--help"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if "invalid choice" in result.stderr:
                bad.append(f"{path}: `{line}` → {result.stderr.strip().splitlines()[-1]}")
    assert not bad, (
        "Init-emitted workflow lines reference non-existent atdd subcommands:\n"
        + "\n".join(bad)
    )
