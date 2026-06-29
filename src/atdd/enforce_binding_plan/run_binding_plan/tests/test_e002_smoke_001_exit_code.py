# URN: test:enforce-binding-plan:run-binding-plan:E002-SMOKE-001-exit-code
# Acceptance: acc:enforce-binding-plan:E002-SMOKE-001-exit-code
# WMBT: wmbt:enforce-binding-plan:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E002-SMOKE-001 — one command, a correct aggregate exit code (V2).

A single ``atdd enforce`` invocation scans the consumer's production code for
all bound rules and maps the aggregate verdict to a process exit code:

  * a clean tree                       -> exit 0
  * one ``coder.logging.print`` viol.  -> exit 1, the rule named at file:line:col
  * a malformed config                 -> exit 2 (usage / wiring error)

Today ``scan.py`` always exits 0 on a successful run regardless of verdict
(its exit code is run-health, not a verdict — SMOKE-TEST-INSTALL §3 step 11).

RED reason: the ``atdd enforce`` verb is absent, so the clean-tree run cannot
return 0 (argparse exits 2 with ``invalid choice: 'enforce'``). When the
verdict bridge ships, the three fixtures separate cleanly into 0/1/2.
"""
from __future__ import annotations

import re

import pytest

from .conftest import VERB_ABSENT

pytestmark = pytest.mark.smoke

# A violation must be reported at a concrete source location: file:line:col.
_FILE_LINE_COL = re.compile(r"[^\s:]+\.py:\d+:\d+")


def _write_consumer(root, body: str) -> None:
    pkg = root / "src" / "app"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "handler.py").write_text(body, encoding="utf-8")


def test_e002_smoke_001_clean_tree_exits_zero(run_enforce, tmp_path) -> None:
    proj = tmp_path / "clean"
    _write_consumer(proj, "def handle(payload):\n    return payload\n")
    proc = run_enforce([], cwd=proj)
    combined = proc.stdout + proc.stderr

    assert VERB_ABSENT not in combined, "atdd enforce is not wired as a command"
    assert proc.returncode == 0, (
        f"clean tree exited {proc.returncode}, expected 0:\n{combined}"
    )


def test_e002_smoke_001_one_print_violation_exits_one(run_enforce, tmp_path) -> None:
    proj = tmp_path / "dirty"
    _write_consumer(
        proj,
        "def handle(payload):\n    print(payload)  # coder.logging.print violation\n    return payload\n",
    )
    proc = run_enforce([], cwd=proj)
    combined = proc.stdout + proc.stderr

    assert VERB_ABSENT not in combined, "atdd enforce is not wired as a command"
    assert proc.returncode == 1, (
        f"one-violation tree exited {proc.returncode}, expected 1:\n{combined}"
    )
    assert "coder.logging.print" in combined, (
        "the failing rule must be named in the output:\n" + combined
    )
    assert _FILE_LINE_COL.search(combined), (
        "the violation must be located at file:line:col:\n" + combined
    )


def test_e002_smoke_001_malformed_config_exits_two(run_enforce, tmp_path) -> None:
    proj = tmp_path / "broken"
    _write_consumer(proj, "def handle(payload):\n    return payload\n")
    atdd_dir = proj / ".atdd"
    atdd_dir.mkdir(parents=True, exist_ok=True)
    # Invalid YAML -> a usage/wiring error, not a verdict.
    (atdd_dir / "config.yaml").write_text("validators: [: : :\n", encoding="utf-8")
    proc = run_enforce([], cwd=proj)
    combined = proc.stdout + proc.stderr

    assert VERB_ABSENT not in combined, "atdd enforce is not wired as a command"
    assert proc.returncode == 2, (
        f"malformed config exited {proc.returncode}, expected 2 (usage error):\n{combined}"
    )
