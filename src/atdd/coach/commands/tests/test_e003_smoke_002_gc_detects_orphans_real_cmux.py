# URN: test:spawn-agents:transactional-spawn-and-orphan-pane-gc:E003-SMOKE-002-gc-detects-orphans
# Acceptance: acc:spawn-agents:E003-INTEGRATION-002-gc-detects-orphans
# WMBT: wmbt:spawn-agents:E003
# Phase: SMOKE
# Layer: integration
# Harness: smoke/backend
"""E003-SMOKE-002 — `atdd coach gc --dry-run` verified against REAL cmux.

SMOKE: no mocks. Builds a real fixture in a throwaway cmux workspace
(never workspace:1; closed afterwards): 4 real panes — 2 renamed to
canonical agent names and recorded in a real `decisions.jsonl`, plus 2
renamed to the default `~/Github/atdd` cwd and left unreferenced.

`atdd coach gc --workspace <scratch> --dry-run` must list exactly the 2
unreferenced default-cwd orphans, leave the 2 decisions.jsonl-referenced
panes off the list, and mutate nothing.

Skips when no cmux daemon is reachable.

Issue #655 — Layer 2: retroactive garbage collection.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time

import pytest

from atdd.coach.commands import coach

pytestmark = [pytest.mark.platform]

_DEFAULT_CWD = "~/Github/atdd"


def _cmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["cmux", *args], capture_output=True, text=True)


def _require_cmux() -> None:
    if shutil.which("cmux") is None:
        pytest.skip("real cmux daemon not available — SMOKE needs real infrastructure")
    if _cmux("list-workspaces").returncode != 0:
        pytest.skip("cmux is installed but no daemon is reachable")


def _surfaces(workspace: str) -> set[str]:
    return set(re.findall(r"surface:\d+", _cmux("list-panels", "--workspace", workspace).stdout))


@pytest.fixture()
def gc_fixture(tmp_path, monkeypatch):
    """Real cmux workspace with 2 referenced + 2 orphan panes, plus a real
    decisions.jsonl. Yields (workspace, referenced_refs, orphan_refs)."""
    _require_cmux()
    out = _cmux("new-workspace", "--name", "ATDD655-smoke-gc", "--cwd", "/tmp").stdout
    match = re.search(r"workspace:\d+", out)
    assert match, f"could not create scratch workspace: {out!r}"
    workspace = match.group(0)
    assert workspace != "workspace:1", "refusing to run SMOKE in workspace:1"
    try:
        refs: list[str] = []
        for _ in range(4):
            pane_out = _cmux("new-pane", "--workspace", workspace).stdout
            refs.append(re.search(r"surface:\d+", pane_out).group(0))
        time.sleep(1)
        referenced, orphans = refs[:2], refs[2:]
        _cmux("rename-tab", "--surface", referenced[0], "--workspace", workspace, "ATDD655-planner")
        _cmux("rename-tab", "--surface", referenced[1], "--workspace", workspace, "ATDD655-coder")
        _cmux("rename-tab", "--surface", orphans[0], "--workspace", workspace, _DEFAULT_CWD)
        _cmux("rename-tab", "--surface", orphans[1], "--workspace", workspace, _DEFAULT_CWD)
        time.sleep(1)

        run_dir = tmp_path / ".atdd" / "runtime" / "coach" / "run-655"
        run_dir.mkdir(parents=True)
        (run_dir / "decisions.jsonl").write_text(
            "\n".join(
                json.dumps({
                    "decision_id": ref,
                    "timestamp": "2026-05-16T10:00:00Z",
                    "coach_run_id": "coach-run-655",
                    "issue_number": 655,
                    "decision_type": "agent_spawned",
                    "inputs": {"agent_id": "agent-655"},
                    "outcome": {"status": "SPAWNED", "surface_ref": ref},
                })
                for ref in referenced
            ) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("ATDD_REPO_ROOT", str(tmp_path))
        yield workspace, referenced, orphans
    finally:
        _cmux("close-workspace", "--workspace", workspace)


def test_gc_dry_run_lists_exactly_the_orphans_in_real_cmux(gc_fixture, capsys):
    workspace, referenced, orphans = gc_fixture

    exit_code = coach.run_cli(["gc", "--workspace", workspace, "--dry-run"])
    out = capsys.readouterr().out

    assert exit_code == 0, f"`atdd coach gc --dry-run` exited {exit_code}"

    for ref in orphans:
        assert ref in out, f"orphan {ref} not listed by gc --dry-run.\n{out}"
    for ref in referenced:
        assert ref not in out, (
            f"{ref} is decisions.jsonl-referenced but gc flagged it as an orphan.\n{out}"
        )

    # --dry-run mutates nothing: both orphan panes are still live in cmux.
    live = _surfaces(workspace)
    for ref in orphans:
        assert ref in live, f"--dry-run closed {ref} — it must only list, not mutate"
