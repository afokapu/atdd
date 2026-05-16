# URN: test:spawn-agents:transactional-spawn-and-orphan-pane-gc:E003-SMOKE-003-gc-apply-closes
# Acceptance: acc:spawn-agents:E003-INTEGRATION-003-gc-apply-closes
# WMBT: wmbt:spawn-agents:E003
# Phase: SMOKE
# Layer: integration
# Harness: smoke/backend
"""E003-SMOKE-003 — `atdd coach gc --apply` verified against REAL cmux.

SMOKE: no mocks. Same real fixture as E003-SMOKE-002 — a throwaway cmux
workspace (never workspace:1; closed afterwards) with 2 decisions.jsonl-
referenced panes and 2 unreferenced default-cwd orphan panes.

`atdd coach gc --workspace <scratch> --apply` must close exactly the 2
orphan panes; a follow-up real `cmux list-panels` must show them gone
while the 2 referenced panes survive.

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
    out = _cmux("new-workspace", "--name", "ATDD655-smoke-gc-apply", "--cwd", "/tmp").stdout
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


def test_gc_apply_closes_only_orphans_in_real_cmux(gc_fixture, capsys):
    workspace, referenced, orphans = gc_fixture

    # Sanity: all 4 panes are live before gc runs.
    live_before = _surfaces(workspace)
    for ref in referenced + orphans:
        assert ref in live_before, f"fixture pane {ref} missing before gc --apply"

    exit_code = coach.run_cli(["gc", "--workspace", workspace, "--apply"])
    assert exit_code == 0, f"`atdd coach gc --apply` exited {exit_code}"
    capsys.readouterr()

    time.sleep(1)
    live_after = _surfaces(workspace)

    # The 2 unreferenced orphans are closed.
    for ref in orphans:
        assert ref not in live_after, (
            f"orphan {ref} still present after gc --apply — real cmux "
            f"list-panels: {sorted(live_after)}"
        )
    # The 2 decisions.jsonl-referenced panes survive.
    for ref in referenced:
        assert ref in live_after, (
            f"gc --apply wrongly closed the referenced pane {ref} — real cmux "
            f"list-panels: {sorted(live_after)}"
        )
